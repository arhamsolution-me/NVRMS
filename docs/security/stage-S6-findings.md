# Stage S6: Agent Hardening and Adversarial Harness Findings

## 1. Executive Summary

Stage S6 hardened the edge agent runtime against lateral movement, adversarial impersonation, malicious updates, configuration tampering, and internal network scanning (SSRF). An adversarial test harness (`agent/tests/test_adversarial_agent.py`) was created to execute targeted attacks against the agent:
1. **Fake Hub & MITM Interception**: Evaluated rogue CA and intercepted TLS certificates against primary and backup certificate pins.
2. **Revoked Agent Termination**: Validated instant session termination and socket closure when an agent is revoked by the Hub.
3. **Cryptographically Signed Updates & Downgrade Defense**: Replaced HMAC with asymmetric Ed25519 digital signatures and added semantic version downgrade protection with automatic rollback.
4. **Config Tamper Resistance & Safe Failure Mode**: Implemented HMAC-SHA256 configuration MAC verification with strict stream refusal (`ConfigIntegrityError`) upon tamper detection.
5. **SSRF and Pivot Defense**: Bounded discovery probes to private RFC 1918 subnets, blocking loopback addresses, cloud link-local metadata endpoints (`169.254.169.254`), and Hub infrastructure IP pivoting.

---

## 2. Adversarial Scenarios & Mitigations

### Scenario 1: Fake Hub and Active MITM Proxy Rejection
- **Threat**: Attacker uses a rogue CA or dynamic interception proxy (e.g., mitmproxy) to intercept agent traffic.
- **Defense Implemented**: `CertificatePinningVerifier` verifies the presented certificate's SHA-256 fingerprint against primary and backup trusted pins.
- **Evidence**: `test_fake_hub_with_untrusted_cert_rejected` and `test_mitm_proxy_interception_rejected` pass. Any untrusted or rogue cert raises `CertificatePinningError` and fails closed.

### Scenario 2: Revoked Agent Dropped within Seconds
- **Threat**: An agent is decommissioned, stolen, or compromised; an attacker attempts to maintain an active connection.
- **Defense Implemented**: Hub's `agent_manager.revoke_agent` immediately closes the WebSocket connection with code 4003 (`Agent revoked`) and clears active state.
- **Evidence**: `test_revoked_agent_live_connection_dropped` verified immediate closure and disconnection.

### Scenario 3: Firmware / Update Tampering and Version Downgrade
- **Threat**: Attacker tampers with update package bytes or attempts a downgrade attack to roll back the agent to an older version with known vulnerabilities.
- **Defense Implemented**: `AgentUpdater` verifies Ed25519 asymmetric signatures against the trusted public key and checks version semantics (`target_version >= current_version`). If either fails, `UpdateVerificationError` is raised. If health checks fail post-install, it automatically restores the pre-update `.backup` file.
- **Evidence**:
  - `test_valid_ed25519_signed_update_succeeds`: PASSED
  - `test_invalid_signature_rejected`: PASSED
  - `test_version_downgrade_rejected`: PASSED
  - `test_automatic_rollback_on_health_check_failure`: PASSED

### Scenario 4: Configuration Tampering and Safe Failure Mode
- **Threat**: Attacker gains local filesystem access or alters `.env` to redirect agent to malicious stream targets.
- **Defense Implemented**: `ConfigIntegrityManager` computes HMAC-SHA256 MAC over configuration state. If MAC mismatch occurs, the agent sets a persistent `is_tampered` security flag. `AgentStreamManager.start_stream()` asserts integrity before initializing workers, refusing to stream if tampered.
- **Evidence**:
  - `test_config_mac_validation_and_tamper_detection`: PASSED
  - `test_agent_refuses_to_stream_when_tampered`: PASSED

### Scenario 5: SSRF and Internal Network Scanning
- **Threat**: Attacker sends NVR probe commands to scan localhost, loopback services, cloud metadata endpoints (`http://169.254.169.254`), or pivot towards the Hub.
- **Defense Implemented**: `validate_target_ip` checks candidate targets against:
  - Dangerous networks: `169.254.169.254/32`, `169.254.0.0/16`, `0.0.0.0/8`, `224.0.0.0/4`, `255.255.255.255/32`.
  - Loopback networks: `127.0.0.0/8`, `::1/128` (blocked in hardened mode).
  - Explicit infrastructure blocks: Hub IP.
  - Allowed: RFC 1918 private subnets only (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- **Evidence**:
  - `test_loopback_probes_blocked_in_hardened_mode`: PASSED
  - `test_cloud_metadata_endpoints_always_blocked`: PASSED
  - `test_hub_infrastructure_pivot_blocked`: PASSED
  - `test_valid_private_lan_target_allowed`: PASSED

---

## 3. Adversarial Test Suite Summary

| Test Identifier | Adversarial Vector | Expected Result | Actual Result |
|---|---|---|---|
| `test_fake_hub_with_untrusted_cert_rejected` | Rogue CA presentation | Connection refused | PASSED |
| `test_mitm_proxy_interception_rejected` | Interception proxy cert | Handshake failed | PASSED |
| `test_revoked_agent_live_connection_dropped` | Live compromised agent | WS close 4003 | PASSED |
| `test_valid_ed25519_signed_update_succeeds` | Legitimate OTA update | Successfully applied | PASSED |
| `test_invalid_signature_rejected` | Tampered / unsigned package | Verification rejected | PASSED |
| `test_version_downgrade_rejected` | Firmware downgrade attempt | Downgrade blocked | PASSED |
| `test_automatic_rollback_on_health_check_failure` | Broken firmware package | Automatic rollback | PASSED |
| `test_config_mac_validation_and_tamper_detection` | Tampered hub_url | MAC mismatch | PASSED |
| `test_agent_refuses_to_stream_when_tampered` | Streaming under tamper | Stream refused | PASSED |
| `test_loopback_probes_blocked_in_hardened_mode` | 127.0.0.1 probe | SSRF blocked | PASSED |
| `test_cloud_metadata_endpoints_always_blocked` | 169.254.169.254 probe | SSRF blocked | PASSED |
| `test_hub_infrastructure_pivot_blocked` | Hub IP probe | SSRF blocked | PASSED |
| `test_valid_private_lan_target_allowed` | 192.168.1.100 probe | Reachability allowed | PASSED |

**Total Suite**: 13/13 Stage S6 adversarial tests passed. Full agent regression suite: 69/69 passed.
