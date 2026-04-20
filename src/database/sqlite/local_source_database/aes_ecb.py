from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


class AesEcb:
    """A utility class for simple AES-ECB encryption/decryption."""

    @classmethod
    def _cipher(
        cls,
        key: str,
    ) -> Cipher:
        return Cipher(
            algorithms.AES(key=key.encode('utf-8')),
            modes.ECB(),
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
