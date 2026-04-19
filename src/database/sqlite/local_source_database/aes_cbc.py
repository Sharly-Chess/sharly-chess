from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


class AesCbc:
    """A utility class for simple AES-CBC encryption/decryption."""

    @classmethod
    def _cipher(
        cls,
        key: str,
    ) -> Cipher:
        b_key: bytes = key[:16].ljust(16).encode('utf-8')
        return Cipher(
            algorithms.AES(key=b_key),
            modes.CBC(initialization_vector=b_key),
            backend=default_backend(),
        )

    @classmethod
    def encrypt_file(
        cls,
        input_file: Path,
        output_encrypted_file: Path,
        key: str,
    ):
        with open(input_file, 'rb') as file:
            data = file.read()

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()

        encryptor = cls._cipher(key).encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        with open(output_encrypted_file, 'wb') as file:
            file.write(ciphertext)

    @classmethod
    def decrypt_file(
        cls,
        input_encrypted_file: Path,
        output_decrypted_file: Path,
        key: str,
    ):
        with open(input_encrypted_file, 'rb') as file:
            ciphertext = file.read()

        decryptor = cls._cipher(key).decryptor()
        decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()

        with open(output_decrypted_file, 'wb') as file:
            file.write(unpadded_data)
