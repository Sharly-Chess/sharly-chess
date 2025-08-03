from pathlib import Path

from requests import get, Response, HTTPError

from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.fide.fide_database import FideDatabase


def download_federation_url(federation_id: str, flag_file: Path, flag_url) -> bool:
    # Add the User-Agent header to be allowed to download from WikiPedia
    # cf https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
    response: Response = get(
        flag_url,
        allow_redirects=True,
        timeout=5,
        headers={
            'User-Agent': f'Sharly Chess/{SharlyChessConfig.version} ({SharlyChessConfig.url}; {SharlyChessConfig.mail})',
        },
    )
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


def main():
    FideDatabase()._update()
    with FideDatabase() as fide_database:
        federation_ids: set[str] = {
            federation_id for federation_id in fide_database.read_federation_ids()
        }
    undeclared_federation_ids: set[str] = {
        federation_id
        for federation_id in federation_ids
        if federation_id not in SharlyChessConfig.federations
    }
    if undeclared_federation_ids:
        print(
            f'The following federations should be declared in SharlyChessConfig:\n{", ".join(undeclared_federation_ids)}.'
        )
    useless_federation_ids: set[str] = {
        federation_id
        for federation_id in SharlyChessConfig.federations
        if federation_id not in federation_ids
    }
    if useless_federation_ids:
        print(
            f'The following federations are declared in SharlyChessConfig but have no players:\n{", ".join(useless_federation_ids)}.'
        )
    download_federation_flags(federation_ids)
    print('Done.')


if __name__ == '__main__':
    main()
