# Threat Model: CCTV Hub and Edge Agent NVR Platform

**Document Version:** 1.0.0  
**Security Classification:** Critical Infrastructure / Confidential  
**Standard Compliance:** STRIDE, NIST SP 800-53, OWASP Top 10, CWE Top 25  

---

## 1. Introduction and Architectural Boundary

The platform ingests, routes, and displays live RTSP and WebRTC video streams originating from remote on-premise NVRs and IP cameras, delivering them securely to web clients.

```
+---------------------------------------------------------------------------------------------------------+
| [NVR / Cameras] --(Segment A: LAN RTSP)--> [Edge Agent]                                                |
|                                                  |                                                      |
|                                       (Segment B: WAN mTLS + AES-256-GCM Session Tunnel)                |
|                                                  v                                                      |
|                                    [Central Hub & MediaMTX]                                             |
|                                                  |                                                      |
|                                       (Segment C: WebRTC DTLS-SRTP / HTTPS AES-128 HLS)                 |
|                                                  v                                                      |
|                                          [Browser Viewer]                                               |
+---------------------------------------------------------------------------------------------------------+
```

### Trust Boundaries
1. **Boundary 1 (Customer LAN):** Camera network to Edge Agent. Edge Agent acts as the isolation bastion. No inbound ports open facing LAN or WAN.
2. **Boundary 2 (Internet / WAN):** Edge Agent outbound connection over public internet to Central Hub (`wss://` and `rtsps://`/`whip://`). Uncontrolled network path exposed to ISP interception, state actors, and MITM.
3. **Boundary 3 (Central Hub Cloud / On-Prem Ingress):** Ingress gateway terminates TLS, authenticates tokens, evaluates RBAC permissions, and issues stream playback coordinates.
4. **Boundary 4 (Hub to Client Browser):** Public internet transport of WebRTC (DTLS-SRTP) or tokenized encrypted HLS segments to client browser.

---

## 2. Threat Actor Matrix and Attack Analysis

The following 10 threat scenarios define the mandatory defense perimeter for the platform:

| # | Threat Actor | Attacker Capability | Target Assets | Attack Path | Implemented Mitigation | Verification Test | Residual Risk |
|---|---|---|---|---|---|---|---|
| **T1** | **Network Eavesdropper** (ISP, rogue Wi-Fi, transit WAN) | Passive capture of WAN packets between Agent, Hub, and Browser | Video payload, control commands, credentials | Sniffing WAN traffic on ports 443, 8554, 8889; packet inspection for H.264/H.265 NAL units or plaintext RTSP | **Segment B:** Mandatory TLS 1.3 / 1.2-AEAD with TLS certificate pinning, supplemented by defense-in-depth application-layer session encryption (AES-256-GCM / ChaCha20-Poly1305 with ephemeral X25519 ECDH key exchange). **Segment C:** Mandatory WebRTC DTLS-SRTP and HTTPS HLS with AES-128 segment encryption. | `tests/test_stream_encryption.py::test_packet_entropy_and_cipher_verification` | Traffic metadata (packet sizing and cadence) may reveal streaming activity; mitigated by fixed packet batching. |
| **T2** | **Active MITM** | Intercept, modify, downgrade, or redirect traffic | Hub API, Edge Agent control channel, Media server | DNS spoofing, ARP cache poisoning, presentation of fraudulent rogue CA certificates, TLS protocol downgrade | Mutual TLS (mTLS) with Hub-issued private CA certificates for agents. Agent cryptographic pinning of Hub CA fingerprint and backup pin. Hub rejects connections lacking valid agent client certificate. HSTS preload on browser ingress. | `tests/test_transport_security.py::test_rogue_ca_rejection` & `agent/tests/test_security_hardening.py::TestCertificatePinning` | CA private key compromise would allow rogue certificate generation; mitigated by offline Root CA and short-lived subordinate CAs. |
| **T3** | **Stream Hijacker** | Obtains, intercepts, or guesses stream URLs or tokens | Live video feed, audio feed, telemetry HUD | Guessing sequential stream IDs, sniffing expired tokens, reusing captured tokens across multiple sessions | Stream tokens are cryptographic HMAC-SHA256 / Ed25519 signed tokens with 30–60 second maximum TTL, bound to `user_id`, `camera_id`, `tenant_id`, and viewer `session_id`. Tokens include single-use `jti` checked against Redis revocation index. Path identifiers use random UUIDv4 names (no sequential numbers or camera IP leakage). | `tests/test_stream_authorization.py::test_token_reuse_and_forgery_rejection` | Physical shoulder-surfing or screenshotting on user screen; mitigated by dynamic user watermark overlay. |
| **T4** | **Malicious Tenant / User** | Valid authenticated login in Tenant A, attempts access to Tenant B | Other tenants' cameras, recordings, locations, audit logs | IDOR attacks on `/api/v1/cameras/{id}`, `/api/v1/streams/{id}/token`, parameter tampering with foreign UUIDs | Strict multi-tenancy enforced at database query abstraction. Location-scoped queries (`Province -> City -> Area -> Site`). Unauthorized cross-tenant queries return concealed HTTP 404 rather than HTTP 403, eliminating existence leakage. Dynamic RBAC checks on every route. | `tests/test_security_hardening.py::TestIDORAndInjectionGuards::test_cross_tenant_agent_access_concealed_404` | Tenant administrator misconfiguring user permissions; mitigated by principle of least privilege in role presets. |
| **T5** | **Rogue or Stolen Agent** | Physical possession or root compromise of remote agent host | Access to other tenants, lateral publishing, Hub command injection | Using stolen agent credentials to publish fraudulent video to other cameras, read other agent feeds, or issue arbitrary Hub RPCs | Agent credentials isolated by `tenant_id` and `site_id`. Agent can only publish to explicitly assigned camera stream UUIDs. Agent WebSocket gateway rejects any message not in strict command whitelist. Instant revocation endpoint invalidates agent token, client cert, and terminates active streams. | `tests/test_agent_lifecycle.py::TestAgentControlChannel::test_agent_command_dispatch_and_whitelist` | Attacker with physical root access can observe local RTSP traffic on that specific remote site; cannot pivot laterally. |
| **T6** | **Compromised LAN Device** | Local presence on customer camera LAN segment | NVR credentials, raw RTSP feeds, Edge Agent host | ARP spoofing local RTSP traffic, port scanning agent, brute forcing NVR HTTP/RTSP ports | Agent has zero inbound listening ports facing the LAN. NVR credentials stored only on agent in DPAPI/Fernet encrypted machine-bound vault. Agent reaches out to NVR on trusted VLAN. Documented guidance: isolate cameras on separate physical VLAN. | `agent/tests/test_nvr_discovery.py::TestEncryptedNVRVault` | Flat unsegmented customer network allows LAN sniffing of unencrypted RTSP camera-to-agent segment (Segment A). |
| **T7** | **Insider with DB Access** | Read access to Hub PostgreSQL database or backup archives | Stored passwords, tokens, NVR credentials, audit logs | Dumping `users`, `refresh_tokens`, `audit_logs`, or reading raw backup files from disk/S3 | Passwords hashed using Argon2id with server-side pepper stored outside DB. API tokens and enrolment codes stored as SHA-256 hashes only. Database backups encrypted client-side using AES-128-CBC + HMAC-SHA256 authenticated encryption before disk write. | `tests/test_backup_restore.py::TestBackupAndRestoreEngine::test_wrong_encryption_key_rejected` | Malicious super-administrator with memory dump access on Hub host; mitigated by envelope encryption and ephemeral KEKs. |
| **T8** | **Hub Host Intruder** | Host-level shell access to Hub server container | Master keys, active decryption keys, persistent malware | Memory inspection, tampering with application binaries, persistent backdoors | Hub services run in non-root containers with dropped Linux capabilities and read-only root filesystems. Master KEK stored in environment / external vault. Redis and PostgreSQL isolated on dedicated internal bridge networks with strict credentials and TLS. | `tests/test_security_hardening.py::TestEnvelopeEncryption` | Zero-day kernel privilege escalation on host; mitigated by OS hardening, container isolation, and SELinux/AppArmor. |
| **T9** | **Replay Attacker** | Captures and re-sends valid control messages or stream tokens | Stream playback, camera control commands, authentication | Re-sending intercepted `start_stream` or `probe_nvr` WebSocket frames, replaying expired stream tokens | All control frames enforce monotonically increasing sequence numbers and client-generated timestamp validation within a 5-second sliding window. Stream tokens enforce short 60s TTL and single-use `jti` tracked in Redis. | `tests/test_stream_encryption.py::test_anti_replay_sliding_window` & `tests/test_auth.py::TestTokenRotation::test_refresh_token_reuse_detection` | Clock desynchronization beyond 5 seconds could reject valid packets; mitigated by automatic clock drift compensation. |
| **T10** | **Abuser / Scanner** | Uses Edge Agent probe API to scan internal corporate networks | Internal network infrastructure, corporate servers, cloud metadata | Sending `probe_nvr` requests targeting `127.0.0.1`, `169.254.169.254`, or private internal subnets | SSRF Guard intercepts probe targets: strictly denies loopback, cloud metadata IPs, multicast, broadcast, and invalid subnets. Rate limiter enforces maximum 5 probes per minute per agent. Credential attempt throttler prevents NVR lockout. | `agent/tests/test_nvr_discovery.py::TestSSRFGuard` & `agent/tests/test_nvr_discovery.py::TestReachabilityAndLockout` | Legitimate internal NVR on non-standard RFC1918 subnet; accommodated through explicit site subnet validation. |

---

## 3. Segment Security Architecture & Guarantees

### Segment A: Camera / NVR to Edge Agent (Remote LAN)
- **Transport:** RTSP / RTSPS over TCP (interleaved) on local private subnet.
- **Protection Measures:**
  - Auto-detection and preference for RTSPS (TLS) when supported by camera/NVR firmware.
  - Zero inbound listening ports on the Edge Agent.
  - SSRF guard preventing probe targeting of internal infrastructure or cloud metadata endpoints.
  - Machine-bound encrypted credential vault storing device passwords.
- **Residual Risk:** Legacy cameras lacking RTSPS support transmit unencrypted H.264 over the local wire. Mitigated by physical or VLAN network isolation.

### Segment B: Edge Agent to Central Hub (WAN Internet Leg)
- **Transport:** Outbound-only TLS 1.3 / 1.2-AEAD WebSocket (`wss://`) and streaming tunnel (`rtsps://` / `whip://`).
- **Protection Measures:**
  - Mutual TLS (mTLS) with Hub-issued client certificates.
  - Certificate fingerprint pinning preventing rogue CA / proxy interception.
  - Application-layer authenticated payload encryption (AES-256-GCM / ChaCha20-Poly1305) with per-session keys derived via ephemeral X25519 ECDH + HKDF.
  - Sliding-window sequence counters preventing frame or command replay attacks.

### Segment C: Central Hub to Browser (Client View Leg)
- **Transport:** WebRTC with mandatory DTLS-SRTP encryption; HTTPS HLS fallback with AES-128 segment encryption.
- **Protection Measures:**
  - User-bound, short-lived (30–60s) cryptographic stream playback tokens.
  - External MediaMTX authentication webhook enforcing tenant and camera matching.
  - Instant viewer revocation via WebSocket `terminate_stream` push and media server kick upon permission removal.
  - Optional dynamic user/timestamp watermark overlay on video stream.

---

## 4. Key Hierarchy and Cryptographic Primitives

```
+-------------------------------------------------------------+
| Root Master KEK (AES-256-GCM / Vault / HSM / Offline Env)    |
|   |                                                         |
|   +--> Database DEK (Envelope Encryption for Stored Secrets)|
|   |                                                         |
|   +--> Internal CA Private Key (mTLS Agent Certificates)    |
|   |                                                         |
|   +--> JWT / Stream Token Signing Key (Ed25519 / ES256)      |
|   |                                                         |
|   +--> Ephemeral Session Key (X25519 ECDH -> AES-256-GCM)   |
+-------------------------------------------------------------+
```

| Function | Algorithm / Primitive | Key Length / Parameter | Lifetime / Rotation |
|---|---|---|---|
| User Passwords | Argon2id | $m=65536, t=3, p=4$, salt=128-bit + server pepper | Per password reset |
| User Access Tokens | JWT (HS256 / Ed25519) | 256-bit secret / Ed25519 keypair | 15 minutes |
| User Refresh Tokens | Cryptographic Random Bytes + SHA-256 Hash | 256-bit entropy | Rotating per use (family revocation) |
| Stream Playback Tokens | Signed JWT with `jti` | 256-bit secret / Ed25519 keypair | 30–60 seconds |
| Agent Control Channel | Mutual TLS (TLS 1.3) | ECDSA P-256 / Ed25519 | 90 days with auto-renewal |
| Application Stream Session | AES-256-GCM / ChaCha20-Poly1305 | 256-bit symmetric key | Rotated every 1 hour or stream restart |
| Stored Database Secrets | AES-256-GCM Envelope Encryption | 256-bit DEK, 256-bit KEK | KEK rotated with overlap window |
| Database Backup Archives | AES-128-CBC + HMAC-SHA256 | 128-bit cipher + 256-bit HMAC | Rotated per backup schedule |
| OTA Update Signatures | Ed25519 Signature | 256-bit public key embedded | Per firmware release |

---

## 5. Summary of Defense Verification

Every defense documented in this threat model is bound to an automated test case that runs in CI/CD and gates deployment. No security control is theoretical or aspirational.
