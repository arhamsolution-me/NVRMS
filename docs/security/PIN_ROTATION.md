# Zero-Site-Visit TLS Certificate Pin Rotation Runbook

**Standard Operating Procedure (SOP):** SEC-SOP-004  
**Applies To:** Central Hub, Media Server, Edge Agent Fleet  

---

## 1. Overview & Architectural Principle

Edge Agents enforce cryptographic TLS certificate pinning on all outbound connections to the Central Hub and MediaMTX. Pinning prevents rogue certificate authorities, compromised public trust stores, and active WAN MITM interception from decrypting or tampering with stream traffic.

To eliminate the need for manual on-site visits to remote facilities when renewing or rotating TLS certificates, the platform employs a **Dual-Pin Overlap Strategy** (`primary_pin` and `backup_pin`).

```
+-----------------------------------------------------------------------------------+
| Timeline Phase        | Agent Trusted Pins        | Server Active Certificate     |
|-----------------------|---------------------------|-------------------------------|
| Steady State          | Primary: A, Backup: B     | Active: Cert A                |
| Pre-Cutover           | Primary: A, Backup: B     | Active: Cert A                |
| Cutover (Zero Downtime)| Primary: A, Backup: B    | Active: Cert B (matches Backup)|
| Post-Cutover Update   | Primary: B, Backup: C     | Active: Cert B                |
+-----------------------------------------------------------------------------------+
```

---

## 2. Pin Rotation Execution Steps

### Phase 1: Pre-Generation & Backup Pin Provisioning (Day -30)
1. **Generate Future Keypair & Certificate (Cert B):**
   ```bash
   # Generate next cycle ECDSA P-256 certificate
   openssl ecparam -name prime256v1 -genkey -noout -out cert_b.key
   openssl req -new -x509 -key cert_b.key -out cert_b.crt -days 365 \
       -subj "/CN=hub.nvrsms.local/O=NVRSMS"
   ```
2. **Compute SHA-256 Fingerprint for Cert B:**
   ```bash
   openssl x509 -in cert_b.crt -outform der | sha256sum
   # Example Output: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
   ```
3. **Distribute Backup Pin to Agent Fleet:**
   - Over the active secure WebSocket control channel, the Hub pushes a configuration update:
     `{"command": "update_config", "payload": {"backup_cert_fingerprint": "<FINGERPRINT_B>"}}`
   - The Edge Agent stores `backup_cert_fingerprint` in its encrypted local configuration vault.
   - Verify that 100% of the fleet reports `backup_pin_acknowledged`.

---

### Phase 2: Live Server Cutover (Day 0)
1. **Deploy Cert B to Ingress Reverse Proxy / Hub Ingress:**
   - Replace active TLS certificate on Caddy / Nginx / Hub with `cert_b.crt` and `cert_b.key`.
   - Reload Caddy (`caddy reload`).
2. **Autonomous Agent Reconnection:**
   - Agents reconnecting to the Hub receive Cert B during the TLS handshake.
   - `CertificatePinningVerifier` checks Cert B against `pinned_fingerprints`:
     - Match against Primary (Cert A): Failed.
     - Match against Backup (Cert B): **PASSED.**
   - Connection succeeds seamlessly without site intervention or stream drop.

---

### Phase 3: Post-Cutover Consolidation (Day +1)
1. **Promote Backup Pin to Primary:**
   - The Hub issues configuration command:
     - `pinned_cert_fingerprint`: `<FINGERPRINT_B>` (promoted).
     - `backup_cert_fingerprint`: `<FINGERPRINT_C>` (pre-generated future emergency pin).
2. **Archive Retired Cert A:**
   - Revoke or retire Cert A private key.
