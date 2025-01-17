import zipfile
from contextlib import suppress
from pathlib import Path

from requests import get, Response, HTTPError

from common.papi_web_config import PapiWebConfig

FIDE_PLAYERS_URL: str = 'https://ratings.fide.com/download/players_list_legacy.zip'

def download_fide_players() -> Path | None:
    print('Downloading FIDE players...')
    local_zip_file: Path = PapiWebConfig.tmp_dir / 'players_list_legacy.zip'
    with suppress(FileNotFoundError):
        local_zip_file.unlink()
    response: Response = get(FIDE_PLAYERS_URL, allow_redirects=True, timeout=5)
    response.raise_for_status()
    local_zip_file.write_bytes(response.content)
    if not local_zip_file.exists():
        print(f'Could not download FIDE players from [{FIDE_PLAYERS_URL}].')
        return None
    print(f'URL [{FIDE_PLAYERS_URL}] downloaded to [{local_zip_file}].')
    return local_zip_file

def unzip_fide_players(local_zip_file: Path) -> Path | None:
    print('Unzipping archive...')
    local_txt_file = PapiWebConfig.tmp_dir / 'players_list.txt'
    with suppress(FileNotFoundError):
        local_txt_file.unlink()
    with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
        zip_ref.extractall(PapiWebConfig.tmp_dir)
    if not local_txt_file.exists():
        print(f'Could not unzip archive [{local_zip_file}].')
        return None
    print(f'Data unzipped to [{local_txt_file}].')
    return local_txt_file

def read_federations(local_txt_file: Path) -> set[str]:
    print('Reading FIDE players and extracting federations...')
    federation_ids: set[str] = set()
    with open(local_txt_file, 'r') as file:
        first_line: bool = True
        for line in file:
            if first_line:
                first_line = False
                continue
            federation = line[76:79].upper()
            if federation not in federation_ids:
                federation_ids.add(federation)
    print(f'{len(federation_ids)} federations found.')
    return federation_ids

def download_federation_url(federation_id: str, flag_file: Path, flag_url) -> bool:
    response: Response = get(flag_url, allow_redirects=True, timeout=5)
    try:
        response.raise_for_status()
        flag_file.write_bytes(response.content)
    except HTTPError as he:
        print(f'{federation_id}: {he}')
        return False
    return True

def download_federation_flags(federation_ids: set[str]):
    print('Downloading federation flags...')
    flags_dir: Path = Path() / 'src' / 'web' / 'static' / 'images' / 'federations'
    flags_dir.mkdir(exist_ok=True, parents=True)
    for federation_id in federation_ids:
        flag_file: Path = flags_dir / f'{federation_id}.svg'
        flag_url: str = f'https://ratings.fide.com/svg/{federation_id}.svg'
        if not download_federation_url(federation_id, flag_file, flag_url):
            other_url: str | None = None
            match federation_id:
                case 'GRL':
                    other_url = 'https://upload.wikimedia.org/wikipedia/commons/0/09/Flag_of_Greenland.svg'
                case _:
                    pass
            if other_url:
                print(f'Trying another URL for flag [{federation_id}]...')
                download_federation_url(federation_id, flag_file, other_url)

def run():
    if not (local_zip_file := download_fide_players()):
        return
    if not (local_txt_file := unzip_fide_players(local_zip_file)):
        return
    federation_ids: set[str] = read_federations(local_txt_file)
    undeclared_federation_ids: set[str] = {
        federation_id for federation_id in federation_ids if federation_id not in PapiWebConfig.federations
    }
    if undeclared_federation_ids:
        print(f'The following federations should be declared in PapiWebConfig:\n{", ".join(undeclared_federation_ids)}.')
    useless_federation_ids: set[str] = {
        federation_id for federation_id in PapiWebConfig.federations if federation_id not in federation_ids
    }
    if useless_federation_ids:
        print(f'The following federations are declared in PapiWebConfig but have no players:\n{", ".join(useless_federation_ids)}.')
    download_federation_flags(federation_ids)
    print('Done.')

run()