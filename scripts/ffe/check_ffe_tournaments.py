from pathlib import Path
from time import time

from requests import Response, get, HTTPError

from common import TMP_DIR
from common.exception import ImporterError

from common.logger import (
    print_interactive_warning,
    print_interactive_info,
    print_interactive_error,
)
from data.event import Event
from data.input_output.tournament_importer_options import FileOption
from data.loader import EventLoader
from data.pairings.checkers import TournamentCheck, BoardDiff
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_tournament_importers import PapiTournamentImporter

tmp_dir: Path = TMP_DIR / 'ffe_pairings_checker'
tmp_dir.mkdir(exist_ok=True, parents=True)
cache_tll: int = 24 * 3600
first_tournament_id: int = 69600  # 20251023
tournament_count: int = 5000


def get_papi_file_path(
    tournament_ffe_id: int,
) -> Path:
    return tmp_dir / f'{tournament_ffe_id}.papi'


def get_error_file_path(
    tournament_ffe_id: int,
) -> Path:
    return tmp_dir / f'{tournament_ffe_id}.error'


def get_error(
    tournament_ffe_id: int,
) -> str | None:
    error_file_path: Path = get_error_file_path(tournament_ffe_id)
    if error_file_path.exists():
        if time() - error_file_path.lstat().st_mtime < cache_tll:
            with open(error_file_path, 'r') as f:
                return f.read()
        error_file_path.unlink()
    return None


def set_error(
    tournament_ffe_id: int,
    error: str,
) -> None:
    with open(get_error_file_path(tournament_ffe_id), 'w') as f:
        f.write(error)
    print_interactive_warning(error)


def download_papi_file_if_needed(
    tournament_ffe_id: int,
) -> bool:
    papi_file_path: Path = get_papi_file_path(tournament_ffe_id)
    try:
        if papi_file_path.is_file():
            return True
        print_interactive_info('Downloading PAPI file...')
        papi_url: str = f'https://www.echecs.asso.fr/Tournois/Id/{tournament_ffe_id}/{tournament_ffe_id}.papi'
        response: Response = get(papi_url, allow_redirects=True, timeout=5)
        try:
            response.raise_for_status()
            papi_file_path.write_bytes(response.content)
            return True
        except HTTPError as he:
            if response.status_code in [
                404,
            ]:
                set_error(tournament_ffe_id, f'Download error: {response.status_code}')
            else:
                set_error(tournament_ffe_id, f'Download exception: {he}')
            return False
    except BaseException:
        papi_file_path.unlink(missing_ok=True)
        raise


def get_event_uniq_id(
    tournament_ffe_id: int,
) -> str:
    return f'ffe-checker-{tournament_ffe_id}'


def create_event_if_needed(
    tournament_ffe_id: int,
) -> Event | None:
    event_uniq_id: str = get_event_uniq_id(tournament_ffe_id)
    try:
        event_loader = EventLoader()
        if event_uniq_id in event_loader.event_uniq_ids:
            return event_loader.load_event(event_uniq_id)
        if not download_papi_file_if_needed(tournament_ffe_id):
            return None
        print_interactive_info(f'Creating Sharly Chess event [{event_uniq_id}]...')
        EventDatabase(event_uniq_id).create()
        papi_file_path: Path = get_papi_file_path(tournament_ffe_id)
        print_interactive_info('Importing Papi file...')
        event = EventLoader().load_event(event_uniq_id)
        PapiTournamentImporter(
            [
                FileOption(papi_file_path),
            ]
        ).load_tournament(event)
        return event_loader.load_event(event_uniq_id)
    except BaseException:
        EventDatabase(event_uniq_id).file.unlink(missing_ok=True)
        raise


def get_check_file_path(
    tournament_ffe_id: int,
) -> Path:
    return tmp_dir / f'{tournament_ffe_id}.json'


def analyse_if_needed(
    tournament_ffe_id: int,
) -> TournamentCheck | None:
    if error := get_error(tournament_ffe_id):
        print_interactive_warning(error)
        return None
    check_file_path: Path = get_check_file_path(tournament_ffe_id)
    try:
        if check_file_path.exists():
            return TournamentCheck.load_from_file(check_file_path)
        if event := create_event_if_needed(tournament_ffe_id):
            tournament = list(event.tournaments)[0]
            if not tournament.finished:
                set_error(tournament_ffe_id, 'Tournament is not finished.')
                get_papi_file_path(tournament_ffe_id).unlink()
                EventDatabase(event.uniq_id).file.unlink()
                return None
            try:
                tournament_check = TournamentCheck.from_object(tournament)
                for round_ in range(1, tournament.rounds + 1):
                    if (
                        round_pairings_diff
                        := tournament.pairing_variation.engine.pairings_diff(
                            tournament,
                            round_,
                            ignore_order=True,
                        )
                    ):
                        tournament_check.diff[round_] = [
                            BoardDiff.from_objects(
                                read_board,
                                expected_board,
                            )
                            for read_board, expected_board in round_pairings_diff
                        ]
                tournament_check.dump_to_file(check_file_path)
                EventDatabase(event.uniq_id).file.unlink()
                return tournament_check
            except ValueError as ve:
                set_error(tournament_ffe_id, str(ve))
                return None
        else:
            return None
    except BaseException:
        check_file_path.unlink(missing_ok=True)
        raise


def main():
    tournament_checks: list[TournamentCheck] = []
    for tournament_ffe_id in range(first_tournament_id, 0, -1):
        if (
            tournament_ffe_id
            not in [
                # 68834,  # Nr integer not string, fixed by #1380
                # 68833,  # Nr integer not string, fixed by #1380
                # 68832,  # Nr integer not string, fixed by #1380
                # 68831,  # Nr integer not string, fixed by #1380
                # 68830,  # Nr integer not string, fixed by #1380
                # 68829,  # Nr integer not string, fixed by #1380
                68809,  # FideCode = 'Z56538' (arbiter: Havard B03159)
                # 68748,  # FideCode = '\'34179178\'', fixed by #1380
                68724,  # 5 players, 15 rounds => KeyError
                # 68343,  # FideCode = '\'34179178\'', fixed by #1380
                # 68309,  # FideCode = '\'533047308', fixed by #1380
                # 68275,  # FideCode = '\'00296155\'', fixed by #1380
                # 68247,  # FideCode = '\'01367056\'', fixed by #1380
                # 67986,  # FideCode = '\'13327534\'', fixed by #1380
                # 67897,  # FideCode = '\'343468780', fixed by #1380
                # 67885,  # Nr integer not string, fixed by #1380
                # 67604,  # Nr integer not string, fixed by #1380
                # 67603,  # Nr integer not string, fixed by #1380
                # 67495,  # Nr integer not string, fixed by #1380
                # 67434,  # FideCode = '\'34310452\'', fixed by #1380
                67109,  # RapideFide = 'R' LEMAITRE MEDINA GIL Emmanuel Y75920 (arbiter: K Benaddou)
                66906,  # FideCode = '11/01/1987' (arbiter: Havard B03159)
                66291,  ## FideCode = 'CM1' (arbiter: denis vincent)
                65417,  # FideCode = 'Y60696' (arbiter: R Tran)
            ]
        ):
            print_interactive_info(f'Tournament #{tournament_ffe_id}:')
            try:
                if tournament_check := analyse_if_needed(tournament_ffe_id):
                    tournament_check.print()
                    tournament_checks.append(tournament_check)
                    print_interactive_info(
                        f'{len(tournament_checks)} tournaments read.'
                    )
                    if len(tournament_checks) == tournament_count:
                        break
            except ImporterError as ie:
                print_interactive_error(str(ie))
                # raise
                # input_interactive('XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')


if __name__ == '__main__':
    main()
