"""HLS video segment AES-128 encryption and token-authorized key delivery."""

from __future__ import annotations

import secrets
import struct

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from hub_backend.logging_config import get_logger
from hub_backend.security.stream_tokens import verify_stream_token

log = get_logger(__name__)


class HLSSegmentEncryptor:
    """Manages AES-128-CBC HLS segment encryption and token-authorized key serving."""

    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id
        # Ephemeral segment keys mapped by sequence number
        self._keys: dict[int, bytes] = {}
        self._ivs: dict[int, bytes] = {}

    def get_or_create_segment_key(self, sequence_number: int) -> tuple[bytes, bytes]:
        """Obtain or generate a fresh 128-bit key and IV for a specific segment sequence."""
        if sequence_number not in self._keys:
            key = secrets.token_bytes(16)
            iv = struct.pack("!QQ", 0, sequence_number)  # 16-byte IV derived from sequence
            self._keys[sequence_number] = key
            self._ivs[sequence_number] = iv
        return self._keys[sequence_number], self._ivs[sequence_number]

    def encrypt_segment(self, segment_data: bytes, sequence_number: int) -> bytes:
        """Encrypt an MPEG-TS or fragmented MP4 segment using AES-128-CBC with PKCS7 padding."""
        key, iv = self.get_or_create_segment_key(sequence_number)

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(segment_data) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()

    def decrypt_segment(self, encrypted_data: bytes, sequence_number: int) -> bytes:
        """Decrypt an encrypted HLS segment."""
        if sequence_number not in self._keys:
            raise KeyError(f"Key for segment {sequence_number} not found or expired")
        key = self._keys[sequence_number]
        iv = self._ivs[sequence_number]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_data) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded_data) + unpadder.finalize()

    def generate_hls_key_tag(
        self,
        sequence_number: int,
        stream_token: str,
        base_url: str = "https://hub.nvrsms.local",
    ) -> str:
        """Generate HLS #EXT-X-KEY playlist directive with tokenized authenticated key URL."""
        _, iv = self.get_or_create_segment_key(sequence_number)
        iv_hex = f"0x{iv.hex()}"
        key_url = (
            f"{base_url.rstrip('/')}/api/v1/streams/{self.stream_id}/hls/key"
            f"?token={stream_token}&seq={sequence_number}"
        )
        return f'#EXT-X-KEY:METHOD=AES-128,URI="{key_url}",IV={iv_hex}'

    def authorize_key_request(
        self,
        token: str,
        sequence_number: int,
    ) -> bytes:
        """Validate playback token and return the raw 16-byte AES-128 decryption key.

        Raises:
            ValueError: If token is invalid, expired, or unauthorized.
            KeyError: If segment sequence key does not exist.
        """
        payload = verify_stream_token(token)
        # Token camera_id / stream must match
        token_camera_id = payload.get("camera_id")
        if token_camera_id and token_camera_id not in self.stream_id:
            log.warning(
                "hls_key_unauthorized_camera_mismatch",
                stream=self.stream_id,
                token_cam=token_camera_id,
            )
            raise ValueError("Token is not authorized for this stream")

        if sequence_number not in self._keys:
            raise KeyError(f"Key for segment sequence {sequence_number} expired or not found")

        return self._keys[sequence_number]
