# Stage S2 Transport Security Hardening Findings

**Date:** 2026-10-26  
**Auditor:** Autonomous Senior Security Engineer  
**Stage:** S2 (Transport Security Hardening)  
**Status:** PASSED (All Gate Requirements Satisfied)  

---

## 1. Audit Findings & Remediations

1. **Mutual TLS (mTLS) for Edge Agent Fleet**:
   - *Finding*: Agent control channel previously relied solely on Bearer token authentication over TLS. While token was cryptographically hashed, lack of client certificate verification left Hub ingress vulnerable to unauthorized rogue client handshakes.
   - *Remediation*: Implemented an internal Private Certificate Authority (`hub_backend/security/ca.py`) using ECDSA P-256 (`SECP256R1`). Hub issues 90-day x509 client certificates with `ExtendedKeyUsage: client_auth` and Subject `CN=agent-{agent_id}`. Hub verifies certificate signature against Root CA, enforces validity dates, verifies Common Name matches caller agent ID, and checks local certificate revocation list (CRL).

2. **Dual-Pin Overlap Strategy (Zero-Site-Visit Pin Rotation)**:
   - *Finding*: Single pinned certificate hash in the agent created a high operational risk during TLS certificate renewals (requiring simultaneous fleet-wide updates or physical site visits).
   - *Remediation*: Upgraded `CertificatePinningVerifier` (`agent/security/pinning.py`) to maintain a set of trusted pins (`pinned_fingerprints`), supporting both `pinned_fingerprint_sha256` (primary) and `backup_fingerprint_sha256` (secondary). Verifier matches peer DER certificate using `hmac.compare_digest` against either pin, allowing zero-downtime cutover before retirement of old keys. Documented standard operating procedure in `docs/security/PIN_ROTATION.md`.

3. **Plaintext Transport Rejection**:
   - *Finding*: Agent code paths could potentially accept `http://` or `ws://` if misconfigured by operators.
   - *Remediation*: Added explicit transport guards in `agent/client.py` (`AgentClient.get_ws_url` and `enrol_agent`) strictly rejecting unencrypted URLs with `ValueError` unless explicitly running in local test fixtures.

4. **TURN Server (coturn) Hardening**:
   - *Finding*: WebRTC NAT traversal required secure TURN configuration to prevent open-relay proxy abuse, SSRF into internal networks, and denial-of-service.
   - *Remediation*:
     - Created `infra/coturn/turnserver.conf` enforcing `use-auth-secret`, `no-multicast-peers`, strict loopback/link-local/RFC1918 peer relay denial (`denied-peer-ip=127.0.0.0-127.255.255.255`, `169.254.0.0-169.254.255.255`, etc.), TLS listening port 5349, and AEAD ciphers only.
     - Implemented dynamic HMAC-SHA1 session credential generator and validator in `hub_backend/security/turn.py`.
     - Integrated coturn service into `infra/docker-compose.yml`.

5. **Ingress TLS 1.3 / 1.2-AEAD & HSTS Preload**:
   - *Finding*: Reverse proxy Caddyfile lacked explicit cipher restrictions and HSTS preload headers.
   - *Remediation*: Configured `media/Caddyfile` with modern TLS parameters (`protocols tls1.2 tls1.3`, AEAD ciphers only, no 3DES/RC4/CBC), HSTS preload (`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`), security headers, and automatic HTTP-to-HTTPS redirect.

---

## 2. Test Verification Evidence

Automated test suite: `hub-backend/tests/test_transport_security.py` (14/14 tests passing):
- `TestInternalCAAndMutualTLS`:
  - `test_internal_ca_root_and_client_issuance`: PASS
  - `test_client_cert_cn_mismatch_rejected`: PASS
  - `test_rogue_ca_certificate_rejected`: PASS
  - `test_revoked_certificate_rejected`: PASS
- `TestCertificatePinningAndRotation`:
  - `test_pinning_accepts_primary_pin`: PASS
  - `test_zero_site_visit_rotation_accepts_backup_pin`: PASS
  - `test_rogue_ca_fails_closed_when_neither_pin_matches`: PASS
- `TestPlaintextTransportRefusal`:
  - `test_agent_client_refuses_plaintext_ws`: PASS
  - `test_enrol_agent_refuses_plaintext_http`: PASS
- `TestTURNHardening`:
  - `test_generate_and_verify_turn_credentials`: PASS
  - `test_expired_turn_credentials_rejected`: PASS
  - `test_tampered_turn_password_rejected`: PASS
- `TestConfigSecurityGuards`:
  - `test_caddyfile_modern_tls_and_hsts`: PASS
  - `test_coturn_config_hardening`: PASS

Agent regression test suite: `agent/tests/test_security_hardening.py` (4/4 tests passing).

---

## 3. Gate Verification Checklist

| Gate Item | Requirement | Verification Result |
|---|---|---|
| Modern TLS | TLS 1.3/1.2-AEAD enforced everywhere; weak ciphers disabled | **PASS** (Caddyfile and coturn verified) |
| Mutual TLS | Hub private CA issues and verifies agent client certificates | **PASS** (`InternalCA` engine and tests verified) |
| Pinning & Rotation | Dual-pin verification with zero-site-visit rotation SOP | **PASS** (`CertificatePinningVerifier` and `PIN_ROTATION.md`) |
| Plaintext Refusal | Unencrypted `http://` and `ws://` rejected | **PASS** (Agent client raises `ValueError`) |
| Rogue CA Rejection | Mismatched / rogue certificates fail closed | **PASS** (Tests confirm fail-closed rejection) |
| TURN Hardening | coturn hardened with time-limited HMAC credentials and anti-relay rules | **PASS** (coturn config and `turn.py` verified) |
| Regression | Zero breaks to existing platform test suites | **PASS** |
