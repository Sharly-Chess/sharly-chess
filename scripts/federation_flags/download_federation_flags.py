from pathlib import Path

from requests import get, Response, HTTPError

# Import this to avoid circular imports
import plugins.manager  # noqa
from common.i18n import _
from common.logger import print_interactive_error
from common.papi_web_config import PapiWebConfig
from database.sqlite.fide.fide_database import FideDatabase


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
        flag_url: str
        match federation_id:
            case 'NON':
                flag_url = 'https://www.svgrepo.com/download/448108/question.svg'
            case 'FID':
                flag_url = (
                    'https://upload.wikimedia.org/wikipedia/de/2/26/Logo_FIDE.svg'
                )
            case _:
                flag_url = f'https://ratings.fide.com/svg/{federation_id}.svg'
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
    if not FideDatabase(write=True).check():
        print_interactive_error(_('Error while updating the FIDE database.'))
        return
    with FideDatabase() as fide_database:
        federation_ids: set[str] = {
            federation_id for federation_id in fide_database.read_federation_ids()
        }
    undeclared_federation_ids: set[str] = {
        federation_id
        for federation_id in federation_ids
        if federation_id not in PapiWebConfig.federations
    }
    if undeclared_federation_ids:
        print(
            f'The following federations should be declared in PapiWebConfig:\n{", ".join(undeclared_federation_ids)}.'
        )
    useless_federation_ids: set[str] = {
        federation_id
        for federation_id in PapiWebConfig.federations
        if federation_id not in federation_ids
    }
    if useless_federation_ids:
        print(
            f'The following federations are declared in PapiWebConfig but have no players:\n{", ".join(useless_federation_ids)}.'
        )
    download_federation_flags(federation_ids)
    print('Done.')


run()
