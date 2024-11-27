import zipfile
from contextlib import suppress
from pathlib import Path

from requests import get, Response, HTTPError

from common.papi_web_config import TMP_DIR

FIDE_PLAYERS_URL: str = 'https://ratings.fide.com/download/players_list_legacy.zip'

def download_fide_players():
    print('Downloading FIDE players... ', end='')
    local_zip_file: Path = TMP_DIR / 'players_list_legacy.zip'
    with suppress(FileNotFoundError):
        local_zip_file.unlink()
    response: Response = get(FIDE_PLAYERS_URL, allow_redirects=True, timeout=5)
    response.raise_for_status()
    local_zip_file.write_bytes(response.content)
    if not local_zip_file.exists():
        print(f'Could not download FIDE players from [{FIDE_PLAYERS_URL}].')
        return
    print(f'URL [{FIDE_PLAYERS_URL}] downloaded to [{local_zip_file}].')
    print('Unzipping archive... ', end='')
    local_txt_file = TMP_DIR / 'players_list.txt'
    with suppress(FileNotFoundError):
        local_txt_file.unlink()
    with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
        zip_ref.extractall(TMP_DIR)
    if not local_txt_file.exists():
        print(f'Could not unzip archive [{local_zip_file}].')
        return
    print(f'Data unzipped to [{local_txt_file}].')
    print('Reading FIDE players and extracting federations... ', end='')
    federations: list[str] = []
    with open(local_txt_file, 'r') as file:
        first_line: bool = True
        for line in file:
            if first_line:
                first_line = False
                continue
            federation = line[76:79].upper()
            if federation not in federations:
                federations.append(federation)
                print(f'[{federation}] ', end='')
    print(f'{len(federations)} federations found.')
    federations.sort()
    print('Downloading federation flags... ', end='')
    flags_dir: Path = Path() / 'web' / 'static' / 'images' / 'federations'
    flags_dir.mkdir(exist_ok=True, parents=True)
    errors: dict[str, str] = {}
    for federation in federations:
        print(f'[{federation}] ', end='')
        flag_url: str = f'https://ratings.fide.com/svg/{federation}.svg'
        response: Response = get(flag_url, allow_redirects=True, timeout=5)
        try:
            response.raise_for_status()
            flag_file: Path = flags_dir / f'{federation}.svg'
            flag_file.write_bytes(response.content)
        except HTTPError as he:
            errors[federation] = str(he)
    if errors:
        print('')
        print(f'{len(errors)} errors found:')
        for federation, error in errors.items():
            print(f'- {federation}: {error}')
    print('Done')

download_fide_players()
