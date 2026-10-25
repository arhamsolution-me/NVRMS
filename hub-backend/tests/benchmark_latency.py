"""Measure encryption/decryption latency overhead for Segment B AES-256-GCM stream cipher."""

import os
import time
from hub_backend.security.session_crypto import (
    KeyExchangeSession,
    StreamPacketCipher,
)

def run_benchmark():
    # 1. Ephemeral key negotiation
    hub_kx = KeyExchangeSession()
    agent_kx = KeyExchangeSession()

    hub_key, _ = hub_kx.derive_session_keys(agent_kx.public_bytes)
    agent_key, _ = agent_kx.derive_session_keys(hub_kx.public_bytes)
    assert hub_key == agent_key

    agent_cipher = StreamPacketCipher(agent_key, epoch=1)
    hub_cipher = StreamPacketCipher(hub_key, epoch=1)

    # 1080p frame simulated size: 64 KB average
    test_frame = b"\x00\x00\x00\x01\x65" + os.urandom(65536)
    iterations = 1000

    # Warmup
    for _ in range(50):
        enc = agent_cipher.encrypt_frame(test_frame)
        _ = hub_cipher.decrypt_frame(enc)

    # Measure encryption
    t0 = time.perf_counter()
    encrypted_frames = []
    for _ in range(iterations):
        encrypted_frames.append(agent_cipher.encrypt_frame(test_frame))
    t1 = time.perf_counter()
    enc_total_ms = (t1 - t0) * 1000.0
    enc_per_frame_ms = enc_total_ms / iterations

    # Measure decryption
    t2 = time.perf_counter()
    for enc in encrypted_frames:
        _ = hub_cipher.decrypt_frame(enc)
    t3 = time.perf_counter()
    dec_total_ms = (t3 - t2) * 1000.0
    dec_per_frame_ms = dec_total_ms / iterations

    total_added_latency_ms = enc_per_frame_ms + dec_per_frame_ms

    print("=== LATENCY OVERHEAD BENCHMARK (AES-256-GCM Segment B) ===")
    print(f"Sample Frame Size: {len(test_frame)} bytes (64 KB)")
    print(f"Iterations: {iterations}")
    print(f"Average Encryption Latency: {enc_per_frame_ms:.4f} ms/frame")
    print(f"Average Decryption Latency: {dec_per_frame_ms:.4f} ms/frame")
    print(f"Total Added Hop-by-Hop Latency: {total_added_latency_ms:.4f} ms/frame")
    print(f"Budget: 100.0 ms | Within Budget: {total_added_latency_ms < 100.0}")

    return {
        "frame_size_bytes": len(test_frame),
        "iterations": iterations,
        "enc_per_frame_ms": enc_per_frame_ms,
        "dec_per_frame_ms": dec_per_frame_ms,
        "total_added_latency_ms": total_added_latency_ms,
    }

if __name__ == "__main__":
    run_benchmark()
