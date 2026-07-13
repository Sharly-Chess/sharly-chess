import sys
from argparse import ArgumentParser
from pathlib import Path

from common.logger import get_logger

logger = get_logger()

# The release of SignTool installed by the GitHub action
SIGNTOOL_RELEASE = 26100
# The URL where to get the timestamp of the signature
SIGNTOOL_TIMESTAMP_URL = 'http://time.certum.pl'
SIGNTOOL_VERSION = f'10.0.{SIGNTOOL_RELEASE}.0'
SIGNTOOL_DIR = Path(
    f'C:/Program Files (x86)/Windows Kits/10/bin/{SIGNTOOL_VERSION}/x64'
)
SIGNTOOL_EXE = SIGNTOOL_DIR / 'signtool.exe'


def _compact_cmd_output(output: str) -> str:
    return '\n'.join(
        line for line in map(lambda s: s.rstrip(), output.split('\n')) if line
    )


def _signtool_command(params: list[str]) -> tuple[int, str, str]:
    """Run SignTool and return the result code, stdout and stderr as strings"""
    # windows_tools.signtool has no sha1 parameter, needed to sign with
    # a cloud certificate, so the module can not be used.
    # from windows_tools.signtool import SignTool
    # signer: SignTool = SignTool(authority_timestamp_url='http://time.certum.pl')
    # signer.sign(EXE, bitness=64)

    import subprocess

    cmd = [str(SIGNTOOL_EXE)] + params
    logger.info('Running command [%s]...', ' '.join(cmd))
    process = subprocess.run(cmd, capture_output=True, text=True)
    logger.info('Command returned [%d].', process.returncode)

    return (
        process.returncode,
        _compact_cmd_output(process.stdout),
        _compact_cmd_output(process.stderr),
    )


def _signtool_verify_file(file: Path, signed: bool) -> bool:
    """Verify if a file is signed or not signed, return True if as expected.
    Cf https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature"""
    logger.info(
        'Verifying that file [%s] is %s...',
        file,
        'signed' if signed else 'not signed',
    )
    result, out, err = _signtool_command(
        [
            'verify',
            '-pa',
            '-v',
            str(file),
        ],
    )
    correct: bool
    if signed:
        correct = result == 0
    else:
        correct = result != 0
    if correct:
        logger.info(out)
        logger.info(
            'File [%s] is signed.' if signed else 'File [%s] is not signed.', file
        )
    else:
        logger.info(out)
        logger.warning(err)
        logger.error(
            'File [%s] is not signed.' if signed else 'File [%s] is already signed.',
            file,
        )
    return correct


def _signtool_sign_file(file: Path, cert_fingerprint: str) -> bool:
    """Sign the exe, return True if no error while signing."""
    logger.info('Signing file [%s]...', file)
    result, out, err = _signtool_command(
        [
            'sign',
            '-sha1',
            cert_fingerprint,
            '-tr',
            SIGNTOOL_TIMESTAMP_URL,
            '-td',
            'sha256',
            '-fd',
            'sha256',
            str(file),
        ]
    )
    logger.info(out)
    if result == 0:
        logger.info('File [%s] has been successfully signed.', file)
        return True
    logger.warning(err)
    logger.error('Signing file [%s] failed.', file)
    return False


def check_available() -> bool:
    if not sys.platform == 'win32':
        logger.error('You are not using Windows.')
        return False
    if not SIGNTOOL_EXE.exists():
        logger.error(
            f'SignTool program [{SIGNTOOL_EXE}] not found, please install '
            f'the Windows Software Development Kit (SDK) to sign files '
            f'(details at https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).'
        )
        return False
    return True


def sign_file(file: Path, cert_fingerprint: str) -> bool:
    # Verify that the file is not already signed
    if not _signtool_verify_file(file, signed=False):
        return True
    # Sign the file
    if not _signtool_sign_file(file, cert_fingerprint):
        return False
    # Verify that it has been signed
    if not _signtool_verify_file(file, signed=True):
        return False
    return True


if __name__ == '__main__':
    parser = ArgumentParser(description='Sign one or more files.')
    parser.add_argument(
        '--cert-fingerprint',
        type=str,
        help='The SHA1 fingerprint of the certificate.',
        required=True,
    )
    parser.add_argument(
        'files',
        nargs='+',
        help='Path(s) to the file(s) to sign.',
    )
    args = parser.parse_args()
    if not check_available():
        sys.exit(1)
    if not all(sign_file(Path(file), args.cert_fingerprint) for file in args.files):
        logger.error('Signing failed.')
        sys.exit(1)
    sys.exit(0)
