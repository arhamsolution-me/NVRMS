"""Internal Certificate Authority (CA) for Mutual TLS (mTLS) and agent certificate lifecycle."""

from __future__ import annotations

import datetime
import hashlib
import uuid

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from hub_backend.logging_config import get_logger

log = get_logger(__name__)


class InternalCA:
    """Manages Root CA, issues agent client certificates, and verifies mTLS credentials."""

    def __init__(
        self,
        ca_key_pem: bytes | None = None,
        ca_cert_pem: bytes | None = None,
    ) -> None:
        self.backend = default_backend()
        self._revoked_serials: set[int] = set()

        if ca_key_pem and ca_cert_pem:
            from typing import cast

            self.ca_key: ec.EllipticCurvePrivateKey = cast(
                ec.EllipticCurvePrivateKey,
                serialization.load_pem_private_key(ca_key_pem, password=None, backend=self.backend),
            )
            self.ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, backend=self.backend)
        else:
            self.ca_key, self.ca_cert = self._generate_root_ca()

    def _generate_root_ca(self) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        """Generate a new in-memory Root CA keypair and self-signed certificate."""
        key = ec.generate_private_key(ec.SECP256R1(), self.backend)
        now = datetime.datetime.now(datetime.UTC)

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NVRSMS Platform"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Security CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "NVRSMS Root CA"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256(), self.backend)
        )
        log.info("internal_root_ca_initialized", serial=cert.serial_number)
        return key, cert

    @property
    def ca_cert_pem(self) -> str:
        """Get Root CA certificate in PEM format."""
        return self.ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    @property
    def ca_fingerprint_sha256(self) -> str:
        """Get lowercase colonless SHA-256 fingerprint of Root CA certificate."""
        der = self.ca_cert.public_bytes(serialization.Encoding.DER)
        return hashlib.sha256(der).hexdigest().lower()

    def issue_agent_certificate(
        self,
        agent_id: uuid.UUID,
        validity_days: int = 90,
    ) -> dict[str, str]:
        """Issue an mTLS client certificate for an enrolled agent.

        Returns:
            Dictionary containing 'client_cert_pem', 'client_key_pem', 'serial_number', and 'ca_cert_pem'.
        """
        agent_key = ec.generate_private_key(ec.SECP256R1(), self.backend)
        now = datetime.datetime.now(datetime.UTC)
        serial = x509.random_serial_number()

        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NVRSMS Platform"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Edge Fleet"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"agent-{agent_id}"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(agent_key.public_key())
            .serial_number(serial)
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=True,
            )
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(f"agent-{agent_id}")]),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256(), self.backend)
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        key_pem = agent_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        log.info("agent_mtls_cert_issued", agent_id=str(agent_id), serial=str(serial))

        return {
            "client_cert_pem": cert_pem,
            "client_key_pem": key_pem,
            "serial_number": str(serial),
            "ca_cert_pem": self.ca_cert_pem,
            "ca_fingerprint_sha256": self.ca_fingerprint_sha256,
        }

    def verify_agent_certificate(
        self,
        cert_pem: str,
        expected_agent_id: uuid.UUID | None = None,
    ) -> bool:
        """Verify that a client certificate is signed by this CA, not expired, not revoked, and matches agent ID."""
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"), self.backend)
        except Exception as exc:
            log.warning("mtls_cert_parse_failed", error=str(exc))
            return False

        # 1. Check revocation
        if cert.serial_number in self._revoked_serials:
            log.warning("mtls_cert_revoked", serial=cert.serial_number)
            return False

        # 2. Check validity dates
        now = datetime.datetime.now(datetime.UTC)
        if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
            log.warning("mtls_cert_expired_or_not_yet_valid", serial=cert.serial_number)
            return False

        # 3. Check signature against Root CA
        try:
            ca_pub = self.ca_cert.public_key()
            if (
                not isinstance(ca_pub, ec.EllipticCurvePublicKey)
                or cert.signature_hash_algorithm is None
            ):
                return False
            ca_pub.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                ec.ECDSA(cert.signature_hash_algorithm),
            )
        except Exception as exc:
            log.warning("mtls_cert_signature_invalid", error=str(exc))
            return False

        # 4. Check Common Name if expected_agent_id provided
        if expected_agent_id:
            cns = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if not cns or cns[0].value != f"agent-{expected_agent_id}":
                log.warning(
                    "mtls_cert_cn_mismatch",
                    expected=f"agent-{expected_agent_id}",
                    actual=cns[0].value if cns else None,
                )
                return False

        return True

    def revoke_certificate(self, serial_number: int) -> None:
        """Add certificate serial to local revocation list."""
        self._revoked_serials.add(serial_number)
        log.warning("mtls_cert_revoked_by_ca", serial=serial_number)


# Global singleton internal CA
internal_ca = InternalCA()
