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
from sponsoring.certificate import SponsoringCertificate

logger: Logger = get_logger()

CERTIFICATE_FILE = BASE_DIR / 'sponsoring.cert'


class PublicKeyLoader:
    """A utility class to load the public key used to verify the signature of the sponsoring certificate."""

    @classmethod
    def load(cls) -> RSAPublicKey:
        """Returns a public RSA key."""
        public_key = load_pem_public_key(
            b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0NjwXch3xwovefE1OTZ0
poHZTZWyWenhaYUm+kTt4FlzZDHwEsuV+fuC5QWd4vAQL4t6ovKjOlJLoxu6UXkD
nK+C7loyOKms5N9kKeqwoygVZc8kKP6uvudQgHc82aB4FziClY2YCIyYIJa2/hJs
DDUxdVgArB+U+deibNzrxXPuiWBSk/XpCtwrViBr9mJ2IuH5jCwDjobtCcEsrCNR
JreZm96p34Z5/lP3BFAQcDp42Z91kW63L1GKKvchsA6ty8I7gpZY/q8yelF7GrIt
iFy0F3Ro6dBIOS51+WEcU5aeh1jbimCAcM8SEIzOcsElYb9p3yvNxQpIvmX7s0On
ZQIDAQAB
-----END PUBLIC KEY-----"""
        )
        assert isinstance(public_key, RSAPublicKey)
        return public_key


class SponsoringCertificateReader:
    """A utility class to read the sponsoring certificate."""

    @staticmethod
    def read(
        input_file: Path | None = None,
    ) -> SponsoringCertificate | None:
        """Reads the sponsoring certificate file (or input_file). On error, logs an exception and returns None."""
        if input_file is None:
            input_file = CERTIFICATE_FILE
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                sponsoring_data: SponsoringCertificate = (
                    SponsoringCertificate.from_dict(json.load(f))
                )
        except FileNotFoundError as e:
            logger.exception(e)
            return None
        if not sponsoring_data.signature:
            logger.exception(
                InvalidSignature(f'No signature in certificate file [{input_file}].')
            )
            return None
        signature: bytes = bytes.fromhex(sponsoring_data.signature)
        sponsoring_data.signature = None
        try:
            PublicKeyLoader.load().verify(
                signature,
                json.dumps(sponsoring_data.to_dict()).encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except InvalidSignature as e:
            logger.exception(e)
            return None
        return sponsoring_data
