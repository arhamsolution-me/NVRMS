"""Agent-side application-layer stream encryption and key exchange."""

from __future__ import annotations

import struct
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from agent.logging_config import get_logger

log = get_logger(__name__)

MAGIC_HEADER = b"\x4e\x56"
PROTOCOL_VERSION = 1
NONCE_LENGTH = 12
TAG_LENGTH = 16


class AgentStreamCipher:
    """Agent session key exchange and AES-256-GCM frame encryptor."""

    def __init__(self) -> None:
        self.private_key = x25519.X25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.session_key: bytes | None = None
        self.aesgcm: AESGCM | None = None
        self.epoch = 1
        self._seq_counter = 0

    @property
    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes_raw()

    def establish_session(
        self,
        hub_public_bytes: bytes,
        epoch: int = 1,
        salt: bytes | None = None,
    ) -> bytes:
        """Derive session key from Hub X25519 public key."""
        hub_public = x25519.X25519PublicKey.from_public_bytes(hub_public_bytes)
        shared_secret = self.private_key.exchange(hub_public)

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=salt or b"nvrsms-salt-fixed-v1",
            info=b"nvrsms-stream-aes256gcm-v1",
        )
        derived = hkdf.derive(shared_secret)
        self.session_key = derived[:32]
        self.epoch = epoch
        self.aesgcm = AESGCM(self.session_key)
        self._seq_counter = 0
        log.info("agent_stream_session_key_negotiated", epoch=epoch)
        return self.session_key

    def _derive_nonce(self, seq_num: int, epoch: int) -> bytes:
        return struct.pack("!IIQ", 0x4E565253, epoch, seq_num)[:NONCE_LENGTH]

    def encrypt_frame(self, plaintext: bytes) -> bytes:
        """Encrypt video frame into authenticated frame envelope."""
        if not self.aesgcm:
            raise RuntimeError("Session key not established. Call establish_session first.")

        self._seq_counter += 1
        seq_num = self._seq_counter
        timestamp_ms = int(time.time() * 1000)

        header = struct.pack(
            "!2sBHQQ",
            MAGIC_HEADER,
            PROTOCOL_VERSION,
            self.epoch,
            seq_num,
            timestamp_ms,
        )

        nonce = self._derive_nonce(seq_num, self.epoch)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, associated_data=header)
        return header + nonce + ciphertext
