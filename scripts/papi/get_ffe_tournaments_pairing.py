from collections import defaultdict
from pathlib import Path

from requests import Response, get, HTTPError

from common import TMP_DIR
from database.access.papi.papi_database import PapiDatabase, PapiVariable

tmp_dir: Path = TMP_DIR / 'test'

tmp_dir.mkdir(parents=True, exist_ok=True)

tournament_ffe_ids_by_pairing: dict[str, list[int]] = defaultdict(list[int])
n: int = 0
for tournament_ffe_id in range(67138, 0, -1):
    pairing_file: Path = tmp_dir / f'{tournament_ffe_id}.txt'
    if not pairing_file.is_file():
        papi_file: Path = tmp_dir / f'{tournament_ffe_id}.papi'
        if not papi_file.is_file():
            papi_url: str = f'https://www.echecs.asso.fr/Tournois/Id/{tournament_ffe_id}/{tournament_ffe_id}.papi'
            response: Response = get(papi_url, allow_redirects=True, timeout=5)
            try:
                response.raise_for_status()
                papi_file.write_bytes(response.content)
                with PapiDatabase(papi_file) as papi_database:
                    items: dict[str, str] = papi_database.read_variables(
                        [
                            PapiVariable.PAIRING_SYSTEM,
                            PapiVariable.PAIRING_VARIATION,
                        ]
                    )
                    system = items[PapiVariable.PAIRING_SYSTEM]
                    variation = items[PapiVariable.PAIRING_VARIATION]
                    with open(pairing_file, 'wt') as f:
                        f.write(f'{system} / {variation}')
            except HTTPError as he:
                pairing_file.touch()
                if response.status_code in [
                    404,
                ]:
                    print(f'{tournament_ffe_id}: {response.status_code}')
                else:
                    print(f'{tournament_ffe_id}: {he}')
                continue
        with PapiDatabase(papi_file) as papi_database:
            items: dict[str, str] = papi_database.read_variables(
                [
                    PapiVariable.PAIRING_SYSTEM,
                    PapiVariable.PAIRING_VARIATION,
                ]
            )
            system = items[PapiVariable.PAIRING_SYSTEM]
            variation = items[PapiVariable.PAIRING_VARIATION]
            with open(pairing_file, 'wt') as f:
                f.write(f'{system} / {variation}')
    with open(pairing_file, 'r') as f:
        pairing: str = f.read()
        if pairing:
            tournament_ffe_ids_by_pairing[pairing].append(tournament_ffe_id)
            n += 1
            if n and n % 100 == 0:
                print(f'Tournaments downloaded: {n}')
                for pairing, tournament_ffe_ids in sorted(
                    tournament_ffe_ids_by_pairing.items(),
                    key=lambda item: len(item[1]),
                    reverse=True,
                ):
                    print(f'- {pairing}: {len(tournament_ffe_ids)}')
                    if len(tournament_ffe_ids) < 10:
                        for t_ffe_id in tournament_ffe_ids[:5]:
                            print(
                                f'  - https://www.echecs.asso.fr/FicheTournoi.aspx?Ref={t_ffe_id}'
                            )
            if n == 4000:
                break
