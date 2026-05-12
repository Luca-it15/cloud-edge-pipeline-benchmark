import os
import ssl
import sys
import urllib.request


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/health"
    context = None

    if url.startswith("https://"):
        ca_file = os.getenv("TLS_CA_FILE", "")
        context = ssl.create_default_context(cafile=ca_file if ca_file else None)
        cert_file = os.getenv("TLS_CLIENT_CERT_FILE", "")
        key_file = os.getenv("TLS_CLIENT_KEY_FILE", "")
        if cert_file and key_file:
            context.load_cert_chain(cert_file, key_file)

    with urllib.request.urlopen(url, context=context, timeout=2) as response:
        if response.status >= 400:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
