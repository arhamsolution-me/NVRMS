"""Stage S3 Tests: Stream Encryption, Session Key Negotiation, Anti-Replay, and HLS Protection."""

from __future__ import annotations

import os
import uuid

import pytest
from agent.security.stream_cipher import AgentStreamCipher
from cryptography.exceptions import InvalidTag

from hub_backend.security.hls_crypto import HLSSegmentEncryptor
from hub_backend.security.session_crypto import (
    AntiReplayWindow,
    KeyExchangeSession,
    StreamPacketCipher,
    compute_shannon_entropy,
)
from hub_backend.security.stream_tokens import create_stream_token


class TestKeyExchangeAndSessionDerivation:
    """Tests for X25519 ECDH key exchange and HKDF-SHA256 session key derivation."""

    def test_hub_and_agent_derive_identical_session_keys(self) -> None:
        """Hub and Agent exchange X25519 public keys and derive matching 256-bit AES-GCM keys."""
        hub_session = KeyExchangeSession()
        agent_cipher = AgentStreamCipher()

        # Both exchange 32-byte public keys
        hub_pub = hub_session.public_bytes
        agent_pub = agent_cipher.public_bytes
        assert len(hub_pub) == 32
        assert len(agent_pub) == 32

        # Independently derive session keys
        hub_key, hub_auth = hub_session.derive_session_keys(agent_pub)
        agent_key = agent_cipher.establish_session(hub_pub)

        assert len(hub_key) == 32
        assert len(agent_key) == 32
        assert hub_key == agent_key

    def test_different_ephemeral_sessions_produce_distinct_keys(self) -> None:
        """New key exchange sessions generate completely independent keys (Forward Secrecy)."""
        hub1 = KeyExchangeSession()
        hub2 = KeyExchangeSession()
        agent = AgentStreamCipher()

        key1, _ = hub1.derive_session_keys(agent.public_bytes)
        key2, _ = hub2.derive_session_keys(agent.public_bytes)

        assert key1 != key2


class TestApplicationLayerStreamCipher:
    """Tests for AES-256-GCM frame encryption, entropy, and tamper rejection."""

    def test_frame_encrypt_decrypt_roundtrip(self) -> None:
        """Plaintext video frame is encrypted by Agent and decrypted by Hub matching byte-for-byte."""
        hub_session = KeyExchangeSession()
        agent = AgentStreamCipher()

        agent.establish_session(hub_session.public_bytes)
        hub_key, _ = hub_session.derive_session_keys(agent.public_bytes)
        hub_cipher = StreamPacketCipher(session_key=hub_key)

        # Simulate synthetic H.264 IDR video frame
        mock_frame = b"\x00\x00\x00\x01\x67\x42\x00\x1f\x9d\xa0\x14\x01\x6e" + os.urandom(1024)

        packet = agent.encrypt_frame(mock_frame)
        assert len(packet) > len(mock_frame)

        decrypted = hub_cipher.decrypt_frame(packet)
        assert decrypted == mock_frame

    def test_packet_entropy_and_cipher_verification(self) -> None:
        """MANDATORY EVIDENCE: Ciphertext payload exhibits high Shannon entropy (>= 7.8) with zero cleartext NAL/RTSP."""
        hub_session = KeyExchangeSession()
        agent = AgentStreamCipher()
        agent.establish_session(hub_session.public_bytes)

        # Realistic 4KB video stream slice with NAL headers and metadata
        cleartext_nal = (
            b"\x00\x00\x00\x01\x65\x88\x84\x00"
            + b"RTSP/1.0 200 OK\r\nCSeq: 1\r\n"
            + (b"REDACTED_CONFIDENTIAL_PAYLOAD_STRING_" * 20)
            + os.urandom(4096)
        )
        packet = agent.encrypt_frame(cleartext_nal)

        # 1. Entropy verification (>= 7.8 bits/byte indicates indistinguishability from random ciphertext)
        entropy = compute_shannon_entropy(packet)
        assert entropy >= 7.8, f"Ciphertext entropy too low: {entropy} bits/byte"

        # 2. Cleartext leakage scan: No RTSP commands or NAL start codes anywhere in the encrypted packet
        assert b"RTSP/1.0" not in packet
        assert b"CSeq:" not in packet
        assert b"\x00\x00\x00\x01\x65" not in packet
        assert b"REDACTED_CONFIDENTIAL_PAYLOAD" not in packet

    def test_tampered_ciphertext_fails_authentication(self) -> None:
        """Tampering with a single bit in the ciphertext causes InvalidTag exception (fail-closed)."""
        hub_session = KeyExchangeSession()
        agent = AgentStreamCipher()
        agent.establish_session(hub_session.public_bytes)
        hub_key, _ = hub_session.derive_session_keys(agent.public_bytes)
        hub_cipher = StreamPacketCipher(session_key=hub_key)

        mock_frame = b"CONFIDENTIAL_SURVEILLANCE_FRAME_PAYLOAD_12345"
        packet = agent.encrypt_frame(mock_frame)

        # Tamper with byte in the middle of ciphertext
        tampered_byte = bytes([packet[30] ^ 0x01])
        tampered_packet = packet[:30] + tampered_byte + packet[31:]

        with pytest.raises(InvalidTag):
            hub_cipher.decrypt_frame(tampered_packet)


class TestAntiReplayProtection:
    """Tests for sliding window anti-replay filter on media frames and control packets."""

    def test_anti_replay_sliding_window(self) -> None:
        """Window accepts in-order, handles out-of-order within window, and rejects duplicates/old packets."""
        window = AntiReplayWindow(window_size=64)

        # In-order packet arrival
        assert window.check_and_update(1) is True
        assert window.check_and_update(2) is True
        assert window.check_and_update(3) is True

        # REPLAY ATTACK: Resending packet 2 is rejected
        assert window.check_and_update(2) is False

        # Out-of-order arrival within window boundary
        assert window.check_and_update(10) is True  # Jumps to 10
        assert window.check_and_update(7) is True  # Allowed (7 > 10 - 64)
        assert window.check_and_update(7) is False  # Replay of 7 rejected

        # Large jump to packet 100
        assert window.check_and_update(100) is True

        # Packet 10 is now older than boundary (100 - 64 = 36), must be rejected
        assert window.check_and_update(10) is False
        assert window.check_and_update(35) is False

    def test_stream_cipher_anti_replay_rejection(self) -> None:
        """StreamPacketCipher rejects replayed captured packet."""
        hub_session = KeyExchangeSession()
        agent = AgentStreamCipher()
        agent.establish_session(hub_session.public_bytes)
        hub_key, _ = hub_session.derive_session_keys(agent.public_bytes)
        hub_cipher = StreamPacketCipher(session_key=hub_key)

        mock_frame = b"FRAME_DATA_TO_BE_REPLAYED"
        captured_packet = agent.encrypt_frame(mock_frame)

        # First delivery succeeds
        assert hub_cipher.decrypt_frame(captured_packet) == mock_frame

        # Replay of exact same captured packet fails
        with pytest.raises(ValueError, match="Anti-replay rejected packet"):
            hub_cipher.decrypt_frame(captured_packet)


class TestHLSSegmentEncryption:
    """Tests for HLS AES-128 segment encryption and token-authorized key delivery."""

    def test_hls_segment_encrypt_and_decrypt(self) -> None:
        """Segment is encrypted with AES-128-CBC and decrypted cleanly."""
        encryptor = HLSSegmentEncryptor(stream_id="stream-test-cam-01_main")
        raw_segment = os.urandom(2048)

        enc_segment = encryptor.encrypt_segment(raw_segment, sequence_number=1)
        assert len(enc_segment) > len(raw_segment)
        assert enc_segment != raw_segment

        dec_segment = encryptor.decrypt_segment(enc_segment, sequence_number=1)
        assert dec_segment == raw_segment

    def test_hls_key_tag_generation(self) -> None:
        """Playlist directive contains tokenized URL and hex IV."""
        encryptor = HLSSegmentEncryptor(stream_id="cam-xyz_sub")
        tag = encryptor.generate_hls_key_tag(
            sequence_number=42,
            stream_token="jwt_stream_token_sample",
            base_url="https://hub.nvrsms.local",
        )
        assert tag.startswith("#EXT-X-KEY:METHOD=AES-128")
        assert (
            'URI="https://hub.nvrsms.local/api/v1/streams/cam-xyz_sub/hls/key?token=jwt_stream_token_sample&seq=42"'
            in tag
        )
        assert "IV=0x" in tag

    def test_hls_key_authorization_with_valid_and_invalid_tokens(self) -> None:
        """Valid stream token retrieves key; expired or wrong camera token is rejected."""
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        tid = uuid.uuid4()

        encryptor = HLSSegmentEncryptor(stream_id=f"{cid}_main")
        encryptor.get_or_create_segment_key(sequence_number=5)

        # 1. Valid token retrieves key
        valid_tok = create_stream_token(
            user_id=uid, camera_id=cid, tenant_id=tid, stream_type="main"
        )
        key = encryptor.authorize_key_request(token=valid_tok, sequence_number=5)
        assert len(key) == 16

        # 2. Token for wrong camera is rejected
        wrong_cid = uuid.uuid4()
        wrong_tok = create_stream_token(user_id=uid, camera_id=wrong_cid, tenant_id=tid)
        with pytest.raises(ValueError, match="not authorized"):
            encryptor.authorize_key_request(token=wrong_tok, sequence_number=5)

        # 3. Expired token is rejected
        expired_tok = create_stream_token(
            user_id=uid, camera_id=cid, tenant_id=tid, expires_in_seconds=-10
        )
        with pytest.raises(ValueError, match="Invalid or expired stream token"):
            encryptor.authorize_key_request(token=expired_tok, sequence_number=5)
