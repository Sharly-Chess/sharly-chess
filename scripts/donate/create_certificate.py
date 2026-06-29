import json
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from common import BASE_DIR
from scripts.donate.generate_private_key import PRIVATE_KEY_FILE
from donate.certificate import DonationCertificate
from donate.certificate_reader import DonationCertificateReader, CERTIFICATE_FILE

from utils.scripts import init_script

arguments = init_script()


class PrivateKeyLoader:
    """A utility class to load the private key used to sign the donation certificates."""

    @staticmethod
    def load() -> RSAPrivateKey:
        try:
            with open(PRIVATE_KEY_FILE, 'rb') as f:
                private_key = load_pem_private_key(f.read(), password=None)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f'Private key file [{PRIVATE_KEY_FILE}] not found, run script generate_keys.py.'
            ) from e
        if not isinstance(private_key, RSAPrivateKey):
            raise RuntimeError(
                f'Invalid private key file [{PRIVATE_KEY_FILE}], PEM file with a RSA key expected.'
            )
        print(f'Read private key from [{PRIVATE_KEY_FILE}].')
        return private_key


class DonationCertificateCreator:
    """A utility class to create donation certificates."""

    @staticmethod
    def create(
        donation_certificate: DonationCertificate,
        output_file: Path,
    ):
        donation_certificate.date = datetime.now().date()
        data: dict[str, str] = donation_certificate.to_dict()
        signature = PrivateKeyLoader.load().sign(
            json.dumps(data).encode('utf-8'),
            padding=padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
            ),
            algorithm=hashes.SHA256(),
        )
        data |= {
            'signature': signature.hex(),
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
            print(f'Wrote certificate file [{output_file}].')


if __name__ == '__main__':
    parser = ArgumentParser(description='Command creating a donation certificate.')
    parser.add_argument(
        '-e',
        '--email',
        type=str,
        help='the email',
        required=True,
    )
    parser.add_argument(
        '-l',
        '--last-name',
        type=str,
        help='the last name',
        required=True,
    )
    parser.add_argument(
        '-f',
        '--first-name',
        type=str,
        help='the first name',
        required=True,
    )
    parser.add_argument(
        '-o',
        '--output-dir',
        type=str,
        help='the output directory',
    )
    args = parser.parse_args()
    output_dir: Path = Path(BASE_DIR)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        print(f'Option --output-dir not used, defaults to [{output_dir}].')
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir(follow_symlinks=True):
        raise OSError(f'[{output_dir}] is not a folder, exiting.')
    output_file = output_dir / CERTIFICATE_FILE.name
    DonationCertificateCreator.create(
        DonationCertificate(
            email=args.email,
            last_name=args.last_name,
            first_name=args.first_name,
        ),
        output_file=output_file,
    )
    print(f'Reading certificate file [{output_file}]...')
    if donation_data := DonationCertificateReader.read(
        input_file=output_file,
    ):
        print(donation_data)
