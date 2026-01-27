"""
SSL Service - Certificate Generation and Management

Provides functionality for:
- Generating self-signed certificates for local development
- Validating uploaded certificates
- Getting certificate information (expiry, issuer, etc.)
"""

import os
import stat
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress


class SSLService:
    """Service for SSL certificate management."""

    def __init__(self, certs_dir: Path):
        self.certs_dir = certs_dir
        self.default_cert_path = certs_dir / "server.crt"
        self.default_key_path = certs_dir / "server.key"

    def ensure_certs_dir(self):
        """Ensure the certificates directory exists."""
        self.certs_dir.mkdir(parents=True, exist_ok=True)

    def generate_self_signed_cert(
        self,
        hostname: str = "localhost",
        valid_days: int = 365,
        cert_path: Optional[Path] = None,
        key_path: Optional[Path] = None
    ) -> Tuple[Path, Path]:
        """
        Generate a self-signed certificate and private key.

        Args:
            hostname: The hostname for the certificate (default: localhost)
            valid_days: Number of days the certificate is valid (default: 365)
            cert_path: Path to save certificate (default: certs_dir/server.crt)
            key_path: Path to save private key (default: certs_dir/server.key)

        Returns:
            Tuple of (cert_path, key_path)
        """
        self.ensure_certs_dir()

        cert_path = cert_path or self.default_cert_path
        key_path = key_path or self.default_key_path

        # Generate RSA private key (2048-bit)
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Build certificate subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Development"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ABCT Local Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])

        # Build Subject Alternative Names (SAN)
        san_list = [
            x509.DNSName("localhost"),
            x509.DNSName(hostname),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv6Address("::1")),
        ]
        # Add hostname as DNS name if different from localhost
        if hostname != "localhost":
            san_list.append(x509.DNSName(hostname))

        # Build the certificate
        now = datetime.utcnow()
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=valid_days))
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        # Write private key to file
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Set restrictive permissions on private key (600)
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)

        # Write certificate to file
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return cert_path, key_path

    def validate_certificate(
        self,
        cert_path: Path,
        key_path: Path
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a certificate and key pair are valid and match.

        Args:
            cert_path: Path to the certificate file
            key_path: Path to the private key file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Load certificate
            with open(cert_path, "rb") as f:
                cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Load private key
            with open(key_path, "rb") as f:
                key_data = f.read()
            private_key = serialization.load_pem_private_key(
                key_data, password=None, backend=default_backend()
            )

            # Verify the certificate's public key matches the private key
            cert_public_key = cert.public_key()
            private_public_key = private_key.public_key()

            # Compare public key numbers
            cert_numbers = cert_public_key.public_numbers()
            private_numbers = private_public_key.public_numbers()

            if cert_numbers.n != private_numbers.n or cert_numbers.e != private_numbers.e:
                return False, "Certificate and private key do not match"

            # Check if certificate is expired
            now = datetime.utcnow()
            if cert.not_valid_after < now:
                return False, f"Certificate expired on {cert.not_valid_after.isoformat()}"

            # Check if certificate is not yet valid
            if cert.not_valid_before > now:
                return False, f"Certificate not valid until {cert.not_valid_before.isoformat()}"

            return True, None

        except FileNotFoundError as e:
            return False, f"File not found: {e.filename}"
        except ValueError as e:
            return False, f"Invalid certificate or key format: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def get_cert_info(self, cert_path: Path) -> Optional[dict]:
        """
        Get information about a certificate.

        Args:
            cert_path: Path to the certificate file

        Returns:
            Dictionary with certificate info, or None if invalid
        """
        try:
            with open(cert_path, "rb") as f:
                cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Extract subject info
            subject_dict = {}
            for attr in cert.subject:
                subject_dict[attr.oid._name] = attr.value

            # Extract issuer info
            issuer_dict = {}
            for attr in cert.issuer:
                issuer_dict[attr.oid._name] = attr.value

            # Extract SAN
            san_list = []
            try:
                san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                for name in san_ext.value:
                    san_list.append(str(name.value))
            except x509.ExtensionNotFound:
                pass

            # Check validity
            now = datetime.utcnow()
            is_valid = cert.not_valid_before <= now <= cert.not_valid_after
            days_remaining = (cert.not_valid_after - now).days if is_valid else 0

            return {
                "subject": subject_dict,
                "issuer": issuer_dict,
                "serial_number": str(cert.serial_number),
                "not_valid_before": cert.not_valid_before.isoformat(),
                "not_valid_after": cert.not_valid_after.isoformat(),
                "expires_at": cert.not_valid_after.isoformat(),
                "days_remaining": days_remaining,
                "is_valid": is_valid,
                "is_self_signed": cert.subject == cert.issuer,
                "san": san_list,
                "signature_algorithm": cert.signature_algorithm_oid._name
            }

        except FileNotFoundError:
            return None
        except Exception as e:
            return {"error": str(e)}

    def cert_exists(self) -> bool:
        """Check if default certificate files exist."""
        return self.default_cert_path.exists() and self.default_key_path.exists()

    def delete_cert(self, cert_path: Optional[Path] = None, key_path: Optional[Path] = None):
        """Delete certificate and key files."""
        cert_path = cert_path or self.default_cert_path
        key_path = key_path or self.default_key_path

        if cert_path.exists():
            cert_path.unlink()
        if key_path.exists():
            key_path.unlink()


# Create singleton instance (will be initialized with proper path in config)
ssl_service: Optional[SSLService] = None


def get_ssl_service(certs_dir: Path) -> SSLService:
    """Get or create SSL service instance."""
    global ssl_service
    if ssl_service is None:
        ssl_service = SSLService(certs_dir)
    return ssl_service
