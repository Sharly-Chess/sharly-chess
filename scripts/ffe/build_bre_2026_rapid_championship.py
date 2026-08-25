import sys
from pathlib import Path

from requests import Response, get

from common import TMP_DIR
from data.event import Event
from data.input_output.tournament_importer_options import FileOption
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_tournament_importers import PapiTournamentImporter


def run(
    event_uniq_id: str,
    event_name: str,
    tournament_namesby_ffe_id: dict[int, str],
):
    event_database: EventDatabase = EventDatabase(event_uniq_id)
    event_database.file.unlink(missing_ok=True)
    event_database.create()
    print(f'Created event database [{event_database.file}].')
    event: Event = EventLoader().load_event(event_uniq_id)

    with EventDatabase(event_uniq_id, write=True) as sqlite_database:
        sqlite_database.execute('UPDATE `info` SET `name` = ?', (event_name,))
        sqlite_database.commit()
        for tournament_ffe_id, tournament_name in tournament_namesby_ffe_id.items():
            papi_dir: Path = TMP_DIR / Path(__file__).stem
            papi_dir.mkdir(exist_ok=True, parents=True)
            papi_file: Path = papi_dir / f'{tournament_ffe_id}.papi'
            url: str = f'https://www.echecs.asso.fr/Tournois/Id/{tournament_ffe_id}/{tournament_ffe_id}.papi'
            print(f'Downloading [{url}]...')
            response: Response = get(url, allow_redirects=True, timeout=60, stream=True)
            response.raise_for_status()
            if response.status_code != 200:
                print(f'Error code {response.status_code}.')
                sys.exit(1)
            # total = int(response.headers.get('content-length', 0))
            # print(f'Receiving {total / 1_048_576:.1f} MB...')
            received = 0
            with open(papi_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    received += len(chunk)
                    # print(f'Downloaded {received} / {total} bytes.')
            # print(f'Download complete ({received / 1_048_576:.1f} MB).')
            event: Event = EventLoader().load_event(event_uniq_id)
            PapiTournamentImporter([FileOption(papi_file)]).load_tournament(event)
            sqlite_database.execute(
                'SELECT MAX(`id`) as `tournament_id` FROM `tournament`'
            )
            tournament_id = sqlite_database.fetchone()['tournament_id']
            sqlite_database.execute(
                'UPDATE `tournament` set `name` = ? WHERE `id` = ?',
                (tournament_name, tournament_id),
            )
            sqlite_database.commit()
        sqlite_database.execute(
            'UPDATE `player` SET `phone` = ?, `mail` = ?, `owed` = ?, `paid` = ?, `comment` = ?',
            ('', '', 0.0, 0.0, ''),
        )
        sqlite_database.commit()


def main():
    run(
        event_uniq_id='opens_rapides_ligue_bretagne_2026',
        event_name='Opens rapides Ligue de Bretagne 2026',
        tournament_namesby_ffe_id={
            68692: '20250928 Domloup',
            68302: '20250928 Gouesnou',
            68388: '20251005 Mellac',
            69863: '20251206 Redon',
            69987: '20251221 Guichen',
            69612: '20251221 Hennebont',
            69435: '20260104 Rosporden',
            70477: "20260215 Pont-l'Abbé",
            71838: '20260501 Quimper',
            71803: '20260501 Vitré',
            71795: '20260508 Arradon',
            72032: '20260510 Lesneven',
            71635: '20260514 Pacé',
            71603: '20260517 Guingamp',
            71227: '20260524 Huelgoat',
            71719: '20260530 Lorient',
            71919: '20260607 Fouesnant',
            71093: '20260607 Yffiniac',
            71981: '20260612 Brest',
            68814: '20260614 Pléboulle',
            71262: '20260621 Concarneau',
            71505: '20260621 Ploërmel',
            71880: '20260628 Liffré',
            71589: '20260628 Quimperlé',
            71244: '20260803 Perros-Guirec',
        },
    )


if __name__ == '__main__':
    main()
