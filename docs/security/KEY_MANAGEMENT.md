# Key Management and Cryptographic Lifecycle Policy

**Document Version:** 1.0  
**Classification:** Cryptographic Standard Operating Procedure  
**Applies to:** Hub Backend, Edge Agents, MediaMTX, Coturn TURN Server

---

## 1. Key Hierarchy

The NVRSMS platform implements a three-tier envelope encryption key hierarchy:

```
+-------------------------------------------------------+
| Level 1: Root Key / Master KEK                       |
| (Offline, Cloud KMS, AWS KMS, HashiCorp Vault, or HSM) |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| Level 2: Key Encryption Keys (KEKs)                  |
| (Rotatable per environment, labeled by UUID/kid)      |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| Level 3: Data Encryption Keys (DEKs)                  |
| (Per-record or per-database-column AES-256-GCM keys)  |
+-------------------------------------------------------+
```

1. **Root Key / Master Key Encryption Key (KEK):**
   - 256-bit AES key supplied via environment variable `MASTER_KEK` or an external secrets vault (e.g., AWS KMS, HashiCorp Vault).
   - Stored in memory only; never persisted to the database, logs, or git repositories.
2. **Key Encryption Keys (KEKs):**
   - Multi-version KEK dictionary maintained in `EnvelopeEncryptor`.
   - Each KEK is referenced by a unique key ID (`kid`).
   - Supports active encryption with the newest `kid` while maintaining seamless decryption capabilities for existing ciphertext encrypted with older `kid` versions.
3. **Data Encryption Keys (DEKs):**
   - 256-bit AES-GCM keys generated per encrypted payload.
   - Encrypted (wrapped) by the active KEK and stored alongside the ciphertext.

---

## 2. Key Inventory & Rotation Schedule

| Key Type | Algorithm | Purpose | Storage Location | Rotation Cadence | Zero-Downtime Procedure |
|:---|:---|:---|:---|:---|:---|
| **Master KEK** | AES-256-GCM (Fernet) | Envelopes all database DEKs | Environment (`MASTER_KEK`) / Secret Manager | 90 Days | Multi-KEK dictionary with background DEK re-wrapping (`rewrap_dek`) |
| **JWT Signing Key** | HMAC-SHA256 (`HS256`) / Ed25519 | Signs user and viewer tokens | Environment (`SECRET_KEY`) | 30 Days | Key ID (`kid`) overlap window: verify against old & new key for 24h |
| **Internal CA Root** | ECDSA P-256 | Signs agent client certificates | Private Hub CA storage (`internal_ca.pem`) | 365 Days | Dual-pinning agent verifier accepts primary and backup pin |
| **Agent Client Cert** | ECDSA P-256 | Agent mTLS authentication | Local Agent private key storage | 90 Days | Automatic renewal over authenticated mTLS control channel |
| **Stream Session Key** | AES-256-GCM | Encrypts Segment B media frames | Ephemeral in-memory only | 3,600s or on stream restart | Ephemeral X25519 ECDH re-negotiation in-band |
| **TURN Secret** | HMAC-SHA1 | Derives time-limited Coturn tokens | Environment (`TURN_STATIC_AUTH_SECRET`) | 90 Days | Co-exist with previous secret in Coturn config during rollover |
| **Backup Encryption** | AES-256-GCM | Encrypts database backup archives | Environment (`BACKUP_ENCRYPTION_KEY`) | 180 Days | Client-side envelope wrapping before leaving host |
| **Agent Update Key** | Ed25519 | Signs agent update packages | Offline build server private key | 365 Days | Agent binary embeds public key; updates verified before execution |

---

## 3. Zero-Downtime Key Rotation Procedures

### 3.1 Master KEK Rotation & DEK Rewrapping
When rotating the Master KEK:
1. Append the new KEK to `KEY_DICTIONARY` with an incremented `kid` (e.g., `kek_v2`) and update `active_kid = "kek_v2"`.
2. All new database write operations immediately encrypt using `kek_v2`.
3. Background migration worker invokes `EnvelopeEncryptor.rewrap_dek()` across existing encrypted database columns:
   ```python
   new_encrypted_dek = encryptor.rewrap_dek(old_encrypted_dek, old_kid="kek_v1", new_kid="kek_v2")
   ```
4. Once all records are rewrapped to `kek_v2`, `kek_v1` is permanently purged.

### 3.2 Dual-Pin Certificate Rotation (Zero Site Visit)
Edge Agents pin the SHA-256 Subject Public Key Info (SPKI) fingerprint of the Hub CA.
To rotate the Hub CA without dispatching field technicians:
1. Generate new Hub CA root keypair.
2. Calculate the SPKI SHA-256 fingerprint of the new CA public key.
3. Push an agent configuration update setting `secondary_pin = <new_spki_fingerprint>` (primary pin remains active).
4. Verify all agents in fleet report compliance.
5. Switch Hub server certificate to the new CA. Agents automatically transition to verifying against the secondary pin.
6. Push follow-up configuration updating `primary_pin = <new_spki_fingerprint>` and clearing the secondary pin.

---

## 4. Key Isolation & Generation Rules

1. **Private Keys Never Leave Host:**
   - The Agent's private key for mTLS and the machine-bound NVR credential vault key are generated on the local host and never transmitted over the network.
   - The Hub CA private key is restricted to the internal CA service and never exposed over HTTP endpoints.
2. **Ephemeral Session Secrets:**
   - Ephemeral X25519 keys used for Segment B stream encryption exist strictly in volatile memory. They are purged immediately upon stream termination or session key rotation.
3. **No Secrets in Source Control or CI:**
   - All secret scanning tools (`trufflehog`, `gitleaks`) run as automated pre-commit and CI gates. Zero plaintext keys are permitted in repository commits or build container layers.
