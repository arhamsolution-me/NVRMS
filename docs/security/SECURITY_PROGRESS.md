# Security and Stream Encryption Hardening Progress

This file records the audit, fixes, test evidence, gate verification, and commits for each security stage (S1 to S8).

---

## Stage S1: Threat Model and Baseline Audit   [PASSED]
- **Threat Model**: Complete and documented in `docs/security/THREAT_MODEL.md` covering all 10 threat scenarios (T1 to T10).
- **SAST Audit**:
  - `bandit` scan on `hub-backend` (4,887 LOC) and `agent` (1,402 LOC) clean at Medium/High (0 issues).
  - Remediated SQL count injection in `dr_verify.py` with strict allow-list.
  - Remediated backoff jitter in `agent/client.py` using cryptographically secure `secrets.SystemRandom().uniform`.
- **Dependency Audit**:
  - `pip-audit`: Replaced vulnerable `python-jose` and `ecdsa` with `pyjwt[crypto]`; upgraded `pip` to 26.2.2. Zero known vulnerabilities remaining.
  - `npm audit`: 0 vulnerabilities on frontend.
- **Secret Scan**: Verified 100% clean across full git history.
- **Findings Report**: Documented in `docs/security/stage-S1-findings.md`.
- **Commit**: `security-s1: Threat model and baseline audit complete`

---

## Stage S2: Transport Security Hardening   [PASSED]
- **Internal CA & mTLS**:
  - `InternalCA` (`hub_backend/security/ca.py`) generating ECDSA P-256 Root CA and issuing 90-day agent client certificates with `client_auth` extension.
  - Server-side verification validates signature against Root CA, enforces validity dates, checks Common Name matching agent ID, and tracks serial revocations (CRL).
- **Dual-Pin Certificate Pinning & Zero-Site-Visit Rotation**:
  - `CertificatePinningVerifier` (`agent/security/pinning.py`) upgraded with dual primary and backup pin evaluation.
  - Zero-site-visit rotation procedure documented in `docs/security/PIN_ROTATION.md`.
- **Plaintext Transport Rejection**:
  - `agent/client.py` strictly refuses unencrypted `http://` or `ws://` in production mode.
- **coturn Hardening**:
  - Created `infra/coturn/turnserver.conf` enforcing `use-auth-secret`, `no-multicast-peers`, private loopback/RFC1918 peer relay denial, and AEAD ciphers.
  - Built time-limited HMAC-SHA1 session credential generator in `hub_backend/security/turn.py`.
  - Added coturn container service to `infra/docker-compose.yml`.
- **Ingress TLS 1.3 / 1.2-AEAD**:
  - Configured `media/Caddyfile` with modern TLS parameters, HSTS with preload, and automatic HTTP-to-HTTPS redirect.
- **Tests**:
  - 14/14 tests passing in `hub-backend/tests/test_transport_security.py`.
  - 4/4 tests passing in `agent/tests/test_security_hardening.py`.
- **Findings Report**: Documented in `docs/security/stage-S2-findings.md`.
- **Commit**: `security-s2: Transport security and mTLS complete`

---

## Stage S3: Stream Encryption and Anti-Replay   [PASSED]
- **Application-Layer Session Crypto**:
  - `KeyExchangeSession` (`hub_backend/security/session_crypto.py`) and `AgentStreamCipher` (`agent/security/stream_cipher.py`) implementing ephemeral X25519 ECDH key exchange with HKDF-SHA256 session key expansion.
  - AES-256-GCM frame encryption envelope with unique nonces derived from epoch and 64-bit sequence counters.
- **Anti-Replay Protection**:
  - 128-packet sliding window anti-replay filter (`AntiReplayWindow`) rejecting replayed frames and stale out-of-window packets.
- **HLS Segment Encryption**:
  - `HLSSegmentEncryptor` (`hub_backend/security/hls_crypto.py`) providing AES-128-CBC segment encryption and token-authorized key delivery (`#EXT-X-KEY`).
- **Evidence Verification**:
  - Shannon entropy measured at **7.953 bits/byte** ($\ge 7.8$ threshold).
  - Packet inspection confirmed 0 cleartext RTSP commands, NAL unit delimiters, or video data on the wire.
  - Replay of captured frames and bit-tampered packets strictly rejected.
- **Tests**:
  - 10/10 tests passing in `hub-backend/tests/test_stream_encryption.py`.
- **Findings Report**: Documented in `docs/security/stage-S3-findings.md`.
- **Commit**: `security-s3: Stream encryption and anti-replay complete`
