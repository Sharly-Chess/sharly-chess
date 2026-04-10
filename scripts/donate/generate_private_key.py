from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from common import BASE_DIR

# ==================================================================
# /!\ WARNING
# THIS PROGRAM SHOULD BE RUN ONLY ONCE AND THE PRIVATE CERTIFICATE
# USED BY THE MAINTAINERS AND THE SHARLY-CHESS.COM PLATFORM ONLY.
# ==================================================================

# 1. Generate the private key used to sign the donation certificates.
# 2. Update the source file of the donation certificate reader
# with the public key to verify the signature of the certificate


PRIVATE_KEY_FILE: Path = Path(__file__).parent / 'donation-private-key.pem'
READER_SOURCE_FILE: Path = BASE_DIR / 'src' / 'donate' / 'certificate_reader.py'


if __name__ == '__main__':
    if PRIVATE_KEY_FILE.exists():
        raise RuntimeError(f'File [{PRIVATE_KEY_FILE}] already exists, exiting.')
    # Generate the private key
    private_key: RSAPrivateKey = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Store the private key to disk
    private_pem: bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(PRIVATE_KEY_FILE, 'wb') as f:
        f.write(private_pem)
    private_pem_string: str = private_pem.decode('utf-8')
    print(f'Private key written to [{PRIVATE_KEY_FILE}].')
    # Update the certificate reader
    public_pem_lines: list[str] = list(
        map(
            lambda s: f'{s}\n',
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode('utf-8')
            .split('\n')[1:-2],
        )
    )
    reader_source_lines: list[str] = []
    with open(READER_SOURCE_FILE, 'r') as f:
        inside_pem: bool = False
        for line in f.readlines():
            if inside_pem:
                if line.__contains__('-----END PUBLIC KEY-----'):
                    reader_source_lines += public_pem_lines
                    reader_source_lines.append(line)
                    inside_pem = False
            else:
                reader_source_lines.append(line)
                if line.__contains__('-----BEGIN PUBLIC KEY-----'):
                    inside_pem = True
    with open(READER_SOURCE_FILE, 'w') as f:
        f.write(''.join(reader_source_lines))
    print(f'Source file [{READER_SOURCE_FILE}] has been updated.')
