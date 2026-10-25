# System Security Model & Cryptographic Architecture

**Document Version:** 1.0  
**Classification:** Technical Security Architecture Specification  
**System:** NVRSMS CCTV Platform (Hub & Edge Agent)  
**Status:** Approved & Enforced

---

## 1. Overview & Trust Boundaries

The NVRSMS platform connects heterogeneous on-premise IP cameras and Network Video Recorders (NVRs) across remote physical locations to authorized operators via modern web browsers. 

The security architecture divides the data and control flow into three distinct operational segments:

```
+------------------+         (A) LAN RTSP         +------------------+
|   Camera / NVR   | ---------------------------> |    Edge Agent    |
+------------------+                              +------------------+
                                                           |
                                                           | (B) mTLS 1.3 + Dual Pinning
                                                           |     + Application AES-256-GCM
                                                           v
+------------------+        (C) DTLS-SRTP         +------------------+
|  Viewer Browser  | <--------------------------- |  Hub MediaMTX    |
+------------------+       WebRTC / HLS AES-128   +------------------+
```

---

## 2. Segment Analysis & Threat Mitigations

### 2.1 Segment A: Camera / NVR to Edge Agent (Remote Physical LAN)

*Physical environment:* On-premise enterprise, industrial, or commercial local area network.

#### Protection Implementation
1. **Protocol Auto-Negotiation:** The Edge Agent auto-detects device capabilities during discovery and strictly prefers RTSPS (port 322/554 over TLS) or HTTPS/ONVIF-over-TLS if supported by the NVR.
2. **Local Segment Placement:** The Edge Agent runs as a dedicated service co-located inside the same Layer-2 network segment as the NVR, eliminating WAN routing for this segment.
3. **No Inbound Listening Ports:** The Edge Agent never opens listening ports on any network interface facing the LAN or WAN (only an optional local loopback `127.0.0.1:8080` status listener). It makes only outbound TLS connections to the Hub.
4. **Credential Isolation:** NVR passwords are stored exclusively on the Agent host in encrypted local storage (Windows DPAPI Machine Scope or AES-256-GCM hardware key). The Hub never stores or receives raw NVR credentials.
5. **SSRF Guard & Probing Safety:** Outbound probes from the Agent strictly filter out loopback (`127.0.0.0/8`, `::1`), link-local metadata endpoints (`169.254.169.254`), and Hub IP ranges. Credential brute-force attempts are limited to 3 per target to prevent NVR account lockout.

#### Honest Architectural Limitation & Network Hygiene Requirements
> **Honest Limitation:** Plain RTSP on legacy IP cameras does not support cryptographic encryption. If legacy hardware transmits unencrypted RTP over the local wire, any device with physical access to that switch segment or an ARP-poisoning attacker could potentially sniff video packets.
> 
> **Enforced Mitigation Requirements:**
> - Deploy cameras and NVRs on an isolated physical VLAN with no routing to corporate LANs or public Wi-Fi.
> - Disable unused legacy protocols (Telnet, UPnP, P2P, SNMPv1/v2, Bonjour) on cameras and NVRs.
> - The Agent audits local subnet configuration and raises security warnings in the Hub UI if it detects default credentials, plaintext-only devices, or flat unsegmented networks with excessive non-camera hosts.

---

### 2.2 Segment B: Edge Agent to Hub (WAN / Internet Leg)

*Physical environment:* Untrusted public internet, commercial ISPs, cellular uplinks, and middleboxes.

#### Cryptographic Architecture
Segment B represents the most critical attack surface. It is protected by dual-layer cryptographic defenses:

1. **Transport-Layer Security (mTLS 1.3):**
   - **Mandatory TLS:** TLS 1.3 mandatory (TLS 1.2 allowed with AEAD ciphers only: `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`, `ECDHE-ECDSA-AES256-GCM-SHA384`). Plaintext HTTP/WS is unconditionally rejected.
   - **Mutual TLS (mTLS):** Edge Agents authenticate using client certificates signed by an internal ECDSA P-256 Certificate Authority (`InternalCA`) managed by the Hub.
   - **Dual Public Key Pinning:** Edge Agents pin the SHA-256 fingerprint of the Hub CA Subject Public Key Info (SPKI). A primary and secondary pin are embedded in the agent configuration to enable zero-site-visit certificate rotation (`docs/security/PIN_ROTATION.md`).
2. **Application-Layer Stream Encryption (Defense-in-Depth):**
   - Even if TLS termination occurs at a reverse proxy or middlebox, the underlying media stream payload is separately encrypted at the application layer before leaving the agent.
   - **Key Agreement:** Ephemeral X25519 Elliptic Curve Diffie-Hellman (ECDH) key exchange negotiated over the authenticated mTLS control channel.
   - **KDF:** HKDF-SHA256 derives a 256-bit AES-GCM session key and authentication key.
   - **Cipher:** AES-256-GCM with unique deterministic nonces (`struct.pack("!IIQ", 0x4E565253, epoch, seq_num)`).
   - **Anti-Replay Window:** A 128-packet sliding window filter drops duplicate sequence numbers or packets older than the window boundary.
   - **Session Key Rotation:** Session keys rotate automatically every 3,600 seconds, on stream restart, or whenever 100,000 frames have been processed.
   - **Zero Cleartext Leakage:** Shannon entropy of transmitted payloads exceeds 7.95 bits/byte (uniform pseudorandom ciphertext). Cleartext RTSP, RTP, and H.264/H.265 NAL start codes are eliminated from WAN packets.

---

### 2.3 Segment C: Hub to Viewer Browser

*Physical environment:* Client browsers over broadband, mobile, or enterprise networks.

#### Transport & Encryption
1. **WebRTC Video (Primary):**
   - Enforces mandatory **DTLS-SRTP** (AES-128-GCM or AES-256-GCM) for real-time video streaming with sub-second glass-to-glass latency.
   - Signaling occurs exclusively over authenticated Secure WebSockets (`wss://`).
2. **HLS Video Fallback (Secondary):**
   - Transmitted exclusively over HTTPS with strict HSTS preload (`max-age=63072000; includeSubDomains; preload`).
   - Each HLS segment (`.ts` or `.m4s`) is encrypted with **AES-128-CBC** (`#EXT-X-KEY:METHOD=AES-128`).
   - Segment encryption keys are served via authenticated ephemeral token endpoints (`/api/v1/streams/hls/key?token=<jwt>`).
   - Token validation verifies `jti`, tenant ID, and camera permissions. Requests without valid tokens receive HTTP 403.
   - HLS segment headers enforce `Cache-Control: no-store, no-cache, must-revalidate`.
3. **Hardened TURN / STUN Infrastructure:**
   - Coturn hardened with time-limited HMAC-SHA1 session credentials (`hub_backend.security.turn`).
   - Open relay disabled (`no-tcp-relay`, `denied-peer-ip` blocking `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`).
   - TLS on TURN (`turns://`) enabled on port 5349.

---

## 3. Hop-by-Hop Decryption vs. End-to-End Encryption (E2EE)

### 3.1 Design Trade-off Rationale
In the current platform architecture, the Hub acts as a multi-tenant media routing engine:
- The Edge Agent streams video upstream to MediaMTX on the Hub.
- MediaMTX performs 1:N fan-out to multiple authorized viewers, transcodes between H.265 and H.264 when browsers lack native decoding, and packages video into WebRTC or HLS.
- Consequently, the Hub **necessarily decrypts** the incoming Segment B stream and **re-encrypts** it for each viewer over DTLS-SRTP or HLS AES-128.

### 3.2 Optional End-to-End Encryption (E2EE) via WebRTC Insertable Streams
For ultra-high-security deployments where the Hub host must be treated as untrusted (Zero-Knowledge Cloud):
- **Mechanism:** WebRTC Insertable Streams (`RTCRtpScriptTransform` / SFrame standard).
- **Architecture:** The Edge Agent encrypts raw encoded video frames before RTP packetization using a per-camera group key. Authorized browser clients receive the decryption key directly over an end-to-end encrypted signaling channel.
- **Trade-off:**
  - Prohibits server-side transcoding (client browser must natively support camera codec, e.g. H.264/H.265).
  - Prohibits server-side AI/ML computer vision inference.
  - Requires modern Chromium/Safari browsers supporting WebRTC Insertable Streams.
- **Status:** The cryptographic primitives (`HKDF`, `AES-256-GCM`, `x25519`) in the platform are modularized to support SFrame key distribution under an optional tenant-level feature flag (`ENABLE_E2EE_INSERTABLE_STREAMS`).

---

## 4. Perimeter Hardening & Supply Chain Security

1. **Non-Root Containers:** All Hub backend and MediaMTX containers run as unprivileged UID 10001 with read-only root filesystems and dropped Linux capabilities (`cap_drop: [ALL]`).
2. **Minimal Exposed Ports:** The platform exposes exclusively port 443 (HTTPS/WSS/WebRTC signaling) and dedicated media ports (`8554` RTSPS, `8889` WebRTC UDP, `5349` TURNS). Databases (PostgreSQL/SQLite) and cache (Redis) bind only to internal loopback or private bridge networks.
3. **Immutable Audit Trail:** All security events (stream starts, token generation, permission toggles, role updates, agent revocations) are recorded in an append-only cryptographic hash chain with SHA-256 digests (`prev_hash` & `record_hash`). Any manual database tampering breaks the cryptographic chain and triggers an alert.
