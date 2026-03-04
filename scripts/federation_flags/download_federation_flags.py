import sys
import tempfile
from pathlib import Path

from requests import get, Response, HTTPError

from common.logger import print_interactive_error, print_interactive_warning
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.fide.fide_database import FideDatabase
from utils import Utils


def download_federation_url(federation_id: str, flag_file: Path, flag_url) -> bool:
    # Add the User-Agent header to be allowed to download from WikiPedia
    # cf https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
    response: Response = get(
        flag_url,
        allow_redirects=True,
        timeout=5,
        headers={
            'User-Agent': f'Sharly Chess/{SharlyChessConfig.version} ({SharlyChessConfig.web_url}; {SharlyChessConfig.mail})',
        },
    )
    try:
        response.raise_for_status()
        flag_file.write_bytes(response.content)
    except HTTPError as he:
        print_interactive_error(f'{federation_id}: {he}')
        return False
    return True


defined_flag_url_by_federation_id = {
    # Not existing
    'NON': 'https://www.svgrepo.com/download/448108/question.svg',
    'FID': 'https://upload.wikimedia.org/wikipedia/de/2/26/Logo_FIDE.svg',
    'TGA': 'https://upload.wikimedia.org/wikipedia/commons/9/9a/Flag_of_Tonga.svg',
    'CAF': 'https://upload.wikimedia.org/wikipedia/commons/6/6f/Flag_of_the_Central_African_Republic.svg',
    # Heavy FIDE flags, replaced by less heavy files or simplified versions (ex: civil ensign)
    'DOM': 'https://upload.wikimedia.org/wikipedia/commons/2/2e/Civil_Ensign_of_the_Dominican_Republic.svg',
    'SRB': 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Flag_of_Serbia.svg',
    'BOL': 'https://upload.wikimedia.org/wikipedia/commons/4/48/Flag_of_Bolivia.svg',
    'BIZ': 'https://upload.wikimedia.org/wikipedia/commons/e/e7/Flag_of_Belize.svg',
    'PER': 'https://upload.wikimedia.org/wikipedia/commons/c/cf/Flag_of_Peru.svg',
    'ESP': 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Bandera_de_Espa%C3%B1a_%28sin_escudo%29.svg',
    'GUA': 'https://upload.wikimedia.org/wikipedia/commons/f/fe/Civil_ensign_of_Guatemala.svg',
    'AND': 'https://upload.wikimedia.org/wikipedia/commons/0/0b/Flag_of_Andorra_%28civil%29.svg',
}


def main():
    FideDatabase()._update()
    with FideDatabase() as fide_database:
        federation_ids = sorted(fide_database.read_federation_ids())
    sc_federation_ids = SharlyChessConfig().federations.keys()
    undeclared_federation_ids: set[str] = {
        federation_id
        for federation_id in federation_ids
        if federation_id not in sc_federation_ids
    }
    if undeclared_federation_ids:
        print_interactive_warning(
            'The following federations should be declared in SharlyChessConfig:\n'
            + ', '.join(undeclared_federation_ids)
        )
    useless_federation_ids: set[str] = {
        federation_id
        for federation_id in sc_federation_ids
        if federation_id not in federation_ids
    }
    if useless_federation_ids:
        print_interactive_warning(
            'The following federations are declared in SharlyChessConfig but have no players:\n'
            + ', '.join(useless_federation_ids)
        )
    print('Downloading federation flags...')
    flags_dir: Path = Path() / 'src' / 'web' / 'static' / 'images' / 'federations'
    flags_dir.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        failed_federation_ids: list[str] = []
        for federation_id in federation_ids:
            print(f'Downloading {federation_id}.svg...')
            file_name = f'{federation_id}.svg'
            tmp_file = Path(tmp_dir) / file_name
            flag_url = defined_flag_url_by_federation_id.get(
                federation_id, f'https://ratings.fide.com/svg/{federation_id}.svg'
            )
            if not download_federation_url(federation_id, tmp_file, flag_url):
                failed_federation_ids.append(federation_id)
            else:
                Utils.run_process(
                    [
                        'scour',
                        '-i',
                        str(tmp_file),
                        '-o',
                        str(flags_dir / file_name),
                        '--enable-viewboxing',
                        '--enable-id-stripping',
                        '--enable-comment-stripping',
                        '--shorten-ids',
                        '--indent=none',
                    ],
                )
        if failed_federation_ids:
            print_interactive_error(
                'Download failed for the following federations:\n'
                + ', '.join(failed_federation_ids)
            )
            sys.exit(1)
    print('Done.')
    sys.exit(0)


if __name__ == '__main__':
    main()
