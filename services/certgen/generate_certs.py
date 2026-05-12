import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


CERT_DIR = Path(os.getenv("CERT_DIR", "/certs"))
FORCE = os.getenv("FORCE_REGENERATE_CERTS", "0") == "1"
VALID_DAYS = int(os.getenv("CERT_VALID_DAYS", "3650"))


def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def subject(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cloud Edge Benchmark"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def certificate_builder(common_name: str, public_key: rsa.RSAPublicKey) -> x509.CertificateBuilder:
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject(common_name))
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
    )


def create_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = private_key()
    cert = (
        certificate_builder("benchmark-local-ca", key.public_key())
        .issuer_name(subject("benchmark-local-ca"))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def create_leaf(
    common_name: str,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    names: list[str],
    client: bool = False,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = private_key()
    san_entries: list[x509.GeneralName] = []
    for name in names:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            san_entries.append(x509.DNSName(name))

    eku = ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH
    cert = (
        certificate_builder(common_name, key.public_key())
        .issuer_name(ca_cert.subject)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def write_leaf(
    name: str,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    sans: list[str],
    client: bool = False,
) -> None:
    key_path = CERT_DIR / f"{name}.key"
    cert_path = CERT_DIR / f"{name}.crt"
    if not FORCE and key_path.exists() and cert_path.exists():
        return
    key, cert = create_leaf(name, ca_key, ca_cert, sans, client=client)
    write_key(key_path, key)
    write_cert(cert_path, cert)


def main() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ca_key_path = CERT_DIR / "ca.key"
    ca_cert_path = CERT_DIR / "ca.crt"

    if FORCE or not ca_key_path.exists() or not ca_cert_path.exists():
        ca_key, ca_cert = create_ca()
        write_key(ca_key_path, ca_key)
        write_cert(ca_cert_path, ca_cert)
    else:
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())

    write_leaf("cloud-api-tls", ca_key, ca_cert, ["cloud-api-tls", "localhost", "127.0.0.1"])
    write_leaf("edge-api-tls", ca_key, ca_cert, ["edge-api-tls", "localhost", "127.0.0.1"])
    write_leaf("client", ca_key, ca_cert, ["benchmark-client"], client=True)
    print(f"certificates ready in {CERT_DIR}")


if __name__ == "__main__":
    main()
