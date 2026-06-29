import json
from logging import Logger
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from common import BASE_DIR
from common.logger import get_logger
from donate.certificate import DonationCertificate

logger: Logger = get_logger()

CERTIFICATE_FILE = BASE_DIR / 'donation.cert'


class PublicKeyLoader:
    """A utility class to load the public key used to verify the signature of the donation certificate."""

    @classmethod
    def load(cls) -> RSAPublicKey:
        """Returns a public RSA key."""
        public_key = load_pem_public_key(
            b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt2e0dEWKJKUO0ssbOUUS
GzYgnLpQu++7Mdwg5tOoOBegpj1c+vFccG6F+Fg3Mym0EOvKBfOmTs11OVkk2oUY
CrhJxWij1lkoNXO0AoUwu7p5Utp8IC+h8ZpaRXElIfTEeXTU6dD9t+2OdBZH612/
hZwW8Ho3OBMbQvbGQv89quIWu6dy8Kxyl8QTtWnowwXUvJ9Wc9kxYqfY0mM0ygMZ
h+hPPGGbxdgy10ijrgoAYlQsP+mtnP2CuEOdb+xAcFlWg58JP9hRytzdwQrEDuLV
O5NOV7f+hTH7brT8IK90EIvyz1T7PwiULU0K63Zn5OUzoltne89TMk4pYtpKoOVi
qQIDAQAB
-----END PUBLIC KEY-----"""
        )
        assert isinstance(public_key, RSAPublicKey)
        return public_key


class DonationCertificateReader:
    """A utility class to read the donation certificate."""

    @staticmethod
    def read(
        input_file: Path | None = None,
    ) -> DonationCertificate | None:
        """Reads the donation certificate file (or input_file). On error, logs an exception and returns None."""
        if input_file is None:
            input_file = CERTIFICATE_FILE
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                donation_data: DonationCertificate = DonationCertificate.from_dict(
                    json.load(f)
                )
        except FileNotFoundError:
            return None
        if not donation_data.signature:
            logger.exception(
                InvalidSignature('No signature in certificate file [%s].', input_file)
            )
            return None
        try:
            signature: bytes = bytes.fromhex(donation_data.signature)
        except ValueError as e:
            logger.error(
                'Invalid signature in certificate file [%s]: %s.', input_file, e
            )
            return None
        donation_data.signature = None
        try:
            PublicKeyLoader.load().verify(
                signature,
                json.dumps(donation_data.to_dict()).encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except InvalidSignature as e:
            logger.exception(e)
            return None
        return donation_data
