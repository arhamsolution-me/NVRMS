"""Application-layer session key negotiation, AES-256-GCM stream encryption, and anti-replay filter."""

from __future__ import annotations

import math
import struct
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from hub_backend.logging_config import get_logger

log = get_logger(__name__)

# Protocol Constants
MAGIC_HEADER = b"\x4e\x56"  # 'NV'
PROTOCOL_VERSION = 1
NONCE_LENGTH = 12
TAG_LENGTH = 16
DEFAULT_WINDOW_SIZE = 128


class KeyExchangeSession:
    """Ephemeral X25519 ECDH key exchange with HKDF-SHA256 session key derivation."""

    def __init__(self) -> None:
        self.private_key = x25519.X25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.epoch = 1
        self.created_at = time.time()

    @property
    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes_raw()

    def derive_session_keys(
        self,
        peer_public_bytes: bytes,
        salt: bytes | None = None,
        info: bytes = b"nvrsms-stream-aes256gcm-v1",
    ) -> tuple[bytes, bytes]:
        """Derive 256-bit AES-GCM session key and 256-bit authentication key from peer public key."""
        peer_public = x25519.X25519PublicKey.from_public_bytes(peer_public_bytes)
        shared_secret = self.private_key.exchange(peer_public)

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=salt or b"nvrsms-salt-fixed-v1",
            info=info,
        )
        derived = hkdf.derive(shared_secret)
        session_key = derived[:32]
        auth_key = derived[32:64]
        return session_key, auth_key


class AntiReplayWindow:
    """Sliding window anti-replay filter for packets and control messages."""

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self.window_size = window_size
        self.highest_seq: int = 0
        self.received_seqs: set[int] = set()

    def check_and_update(self, seq_num: int) -> bool:
        """Check if sequence number is valid and not replayed.

        Returns:
            True if packet is accepted, False if packet is a duplicate or too old.
        """
        if seq_num <= 0:
            return False

        # First packet seen
        if self.highest_seq == 0:
            self.highest_seq = seq_num
            self.received_seqs.add(seq_num)
            return True

        # Packet arrived ahead of current highest sequence
        if seq_num > self.highest_seq:
            self.highest_seq = seq_num
            self.received_seqs.add(seq_num)
            # Prune sequence numbers outside the sliding window
            cutoff = self.highest_seq - self.window_size
            self.received_seqs = {s for s in self.received_seqs if s > cutoff}
            return True

        # Packet is older than the sliding window boundary
        if seq_num <= (self.highest_seq - self.window_size):
            log.warning("anti_replay_packet_too_old", seq=seq_num, highest=self.highest_seq)
            return False

        # Packet is within window: check for duplicate
        if seq_num in self.received_seqs:
            log.warning("anti_replay_duplicate_detected", seq=seq_num)
            return False

        self.received_seqs.add(seq_num)
        return True


class StreamPacketCipher:
    """Encrypts and decrypts media frames using AES-256-GCM with unique deterministic nonces."""

    def __init__(self, session_key: bytes, epoch: int = 1) -> None:
        if len(session_key) != 32:
            raise ValueError("session_key must be exactly 32 bytes (256 bits)")
        self.session_key = session_key
        self.epoch = epoch
        self.aesgcm = AESGCM(session_key)
        self.anti_replay = AntiReplayWindow()
        self._seq_counter: int = 0

    def _derive_nonce(self, seq_num: int, epoch: int) -> bytes:
        """Derive 12-byte nonce from epoch and 64-bit sequence counter."""
        return struct.pack("!IIQ", 0x4E565253, epoch, seq_num)[:NONCE_LENGTH]

    def encrypt_frame(self, plaintext: bytes) -> bytes:
        """Wrap plaintext video frame in authenticated AES-256-GCM envelope."""
        self._seq_counter += 1
        seq_num = self._seq_counter
        timestamp_ms = int(time.time() * 1000)

        # Header: magic (2B), version (1B), epoch (2B), seq_num (8B), timestamp (8B) = 21 Bytes
        header = struct.pack(
            "!2sBHQQ",
            MAGIC_HEADER,
            PROTOCOL_VERSION,
            self.epoch,
            seq_num,
            timestamp_ms,
        )

        nonce = self._derive_nonce(seq_num, self.epoch)
        # Authenticated data binds the unencrypted header to the ciphertext
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, associated_data=header)

        return header + nonce + ciphertext

    def decrypt_frame(self, packet: bytes) -> bytes:
        """Authenticate and decrypt frame envelope.

        Raises:
            ValueError: If packet header is invalid or packet fails anti-replay check.
            InvalidTag: If ciphertext has been tampered with or tag verification fails.
        """
        header_len = 21
        if len(packet) < (header_len + NONCE_LENGTH + TAG_LENGTH):
            raise ValueError("Packet truncated: shorter than minimum frame envelope")

        header = packet[:header_len]
        magic, version, epoch, seq_num, timestamp_ms = struct.unpack("!2sBHQQ", header)

        if magic != MAGIC_HEADER:
            raise ValueError(f"Invalid magic header: expected {MAGIC_HEADER!r}, got {magic!r}")

        if version != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")

        # Anti-replay check
        if not self.anti_replay.check_and_update(seq_num):
            raise ValueError(f"Anti-replay rejected packet with sequence number {seq_num}")

        nonce = packet[header_len : header_len + NONCE_LENGTH]
        ciphertext = packet[header_len + NONCE_LENGTH :]

        # GCM decrypt and verify tag
        return self.aesgcm.decrypt(nonce, ciphertext, associated_data=header)


def compute_shannon_entropy(data: bytes) -> float:
    """Calculate Shannon entropy (in bits per byte) of a byte sequence.

    Ciphertext encrypted with AES-256-GCM should exhibit entropy >= 7.8 (ideal max 8.0).
    Plaintext video frames or text streams exhibit entropy typically between 3.0 and 6.5.
    """
    if not data:
        return 0.0
    frequencies: dict[int, int] = {}
    for byte in data:
        frequencies[byte] = frequencies.get(byte, 0) + 1

    length = len(data)
    entropy = 0.0
    for count in frequencies.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy
