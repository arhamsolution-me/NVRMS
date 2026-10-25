# Security Incident Response Playbooks

**Document Version:** 1.0  
**Classification:** Incident Response Standard Operating Procedures (SOP)  
**System:** NVRSMS Hub Backend & Edge Agent Fleet  
**Status:** Approved & Enforced

---

## 1. Incident Severity Classification Matrix

| Severity Level | Definition | Response SLA | Examples |
|:---|:---|:---|:---|
| **P1 - Critical** | Active compromise of Hub server, Root CA leak, cross-tenant stream exposure, or mass agent hijacking | Immediate (< 15 minutes) | Hub shell obtained, Master KEK leaked, cross-tenant IDOR confirmed |
| **P2 - High** | Single agent compromised, stolen user credentials with active sessions, or isolated stream token leak | < 1 hour | Stolen physical agent hardware, employee account compromised |
| **P3 - Medium** | Brute force attack against login, SSRF probe attempt detected, or anomaly in audit hash chain | < 4 hours | Sustained login rate limit trips, failed tamper integrity alerts |
| **P4 - Low** | Misconfigured camera VLAN, expired diagnostic certificate, or cosmetic header anomaly | < 24 hours | Agent reports plaintext-only NVR on local subnet |

---

## 2. Playbook 1: Stolen or Compromised Edge Agent

*Trigger:* Physical theft of an edge agent appliance, unauthorized shell access on the agent host, or anomalous connection from an unexpected IP address.

### Step 1: Immediate Containment (Revocation)
1. Authenticate as a Hub Administrator with `agents:delete` or `agents:update` permission.
2. Execute immediate agent revocation via REST API:
   ```bash
   curl -X POST https://hub.nvrsms.local/api/v1/agents/{agent_id}/revoke \
     -H "Authorization: Bearer $ADMIN_JWT"
   ```
3. **Automated Platform Action:**
   - The Hub immediately closes active WebSocket connections with code `4003` ("Agent revoked").
   - The Hub drops the agent's enrollment certificate from the active trust list.
   - MediaMTX terminates all publish and read hooks associated with the agent's cameras.
   - Any live stream viewers watching streams routed through this agent are dropped within $< 0.05$ seconds.

### Step 2: Invalidation & Token Cleanup
1. The Hub invalidates all active stream tokens associated with the agent's cameras via `revoke_user_streams(agent_id=agent_id)`.
2. Delete or regenerate the agent enrollment code.

### Step 3: Remote Site NVR Credential Remediation
1. Access the on-premise NVRs previously managed by the compromised agent.
2. Change the RTSP/ONVIF passwords directly on the NVR hardware.
3. If new agent hardware is deployed, re-enroll using a fresh, single-use enrollment code.

---

## 3. Playbook 2: Credential or Token Leak (User JWT / Stream Token)

*Trigger:* User reports stolen device, access token observed in unauthorized proxy logs, or stream URL shared publicly.

### Step 1: Terminate All Active User Sessions
1. Invoke the active session revocation endpoint for the user:
   ```bash
   curl -X DELETE https://hub.nvrsms.local/api/v1/auth/sessions \
     -H "Authorization: Bearer $USER_OR_ADMIN_JWT"
   ```
2. This blacklists all active JWT `jti` identifiers and flushes refresh token families for the user account.

### Step 2: Instant Stream Revocation
1. Call `revoke_user_streams(user_id=target_user_id)`.
2. The Hub broadcasts stream termination signals over WebSocket and instructs MediaMTX to drop all connected viewers associated with the user within 3 seconds.

### Step 3: Password & TOTP Reset
1. Force password reset for the affected user.
2. If TOTP was configured, invalidate current authenticator seed and generate a fresh enrollment QR code.

---

## 4. Playbook 3: Hub Database Dump or Master KEK Leak

*Trigger:* Unauthorized database export detected, database credentials discovered in external breach, or Master KEK compromised.

### Step 1: Isolate Hub Database
1. Restrict database listener to local socket only; verify firewall blocks external TCP ports.
2. Rotate all database service account passwords immediately.

### Step 2: Execute Master KEK Rotation & DEK Rewrapping
1. Generate a new 256-bit Master KEK (`kek_v2`).
2. Update Hub environment variables:
   - `MASTER_KEK_PREVIOUS=<compromised_kek_v1>`
   - `MASTER_KEK=<new_kek_v2>`
3. Run the automated rewrapping utility:
   ```bash
   python -m hub_backend.tools.rotate_keys --rewrap-all
   ```
4. Verify all records decrypt cleanly under `kek_v2`.
5. Remove `MASTER_KEK_PREVIOUS` and restart the Hub backend service.

---

## 5. Playbook 4: Internal CA or Hub Root Certificate Compromise

*Trigger:* Private key of `InternalCA` accessed by unauthorized parties or rogue certificates detected.

### Step 1: Activate Secondary Pin & Emergency CA Generation
1. Generate emergency replacement CA root keypair (`InternalCA_v2`).
2. Deploy new Hub TLS certificate signed by `InternalCA_v2`.
3. Edge Agents configured with dual pinning automatically accept connections if `secondary_pin` matches the new root SPKI fingerprint.
4. For agents requiring update, push signed binary update package via out-of-band management or local provisioning key.

### Step 2: Mass Agent Re-Enrollment
1. Revoke the old CA root.
2. Issue fresh client certificates to all verified edge agents via the secure enrollment endpoint.

---

## 6. Playbook 5: Cross-Tenant Data Isolation Anomaly

*Trigger:* Any alert or log entry indicating an IDOR attempt or cross-tenant resource query.

### Step 1: Immediate Account Suspension
1. Temporarily deactivate the offending user account:
   ```bash
   curl -X PATCH https://hub.nvrsms.local/api/v1/users/{user_id} \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"is_active": false}'
   ```
2. Drop all live streams and active sessions for the user.

### Step 2: Audit Hash Chain Verification
1. Run cryptographic audit chain verification tool:
   ```python
   from hub_backend.security.audit_crypto import verify_audit_log_chain
   is_valid, broken_id = await verify_audit_log_chain(db_session, tenant_id=target_tenant_id)
   ```
2. Confirm whether any unauthorized mutations occurred.
3. Review audit logs for all actions performed by the suspicious account across the preceding 72 hours.
