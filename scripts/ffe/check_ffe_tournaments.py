from pathlib import Path
from time import time

from requests import Response, get, HTTPError

from common import TMP_DIR

from common.logger import (
    print_interactive_warning,
    print_interactive_info,
)
from data.event import Event
from data.input_output.tournament_importer_options import FileOption
from data.loader import EventLoader
from data.pairings.checkers import TournamentCheck, BoardDiff
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_tournament_importers import PapiTournamentImporter

# All the temporary files are stored in this folder:
# - <ffe_id>.papi (Papi download)
# - <ffe_id>-terminated.papi (Papi download for terminated tournaments)
# - <ffe_id>.error (a text file that contains potential errors)
# - <ffe_id>-permanent.error (a text file that contains potential errors, for terminated tournaments)
# - <ffe_id>.json (the result of the analysis)
# - <ffe_id>-terminated.json (the result of the analysis, for terminated tournaments)
tmp_dir: Path = TMP_DIR / 'ffe_pairings_checker'
tmp_dir.mkdir(exist_ok=True, parents=True)

# Downloads, errors and check results are forgotten after 2 days
# for unterminated tournaments, kept permanently for terminated tournaments.
cache_tll: int = 2 * 24 * 3600

# The ID of the first (most recent) tournament on the FFE website
first_tournament_id: int = 69600  # 20251023

# The number of tournaments to check
tournament_count: int = 5000


def get_papi_file_path(
    tournament_ffe_id: int,
) -> Path:
    """Returns the path of the Papi file of the tournament."""
    return tmp_dir / f'{tournament_ffe_id}.papi'


def get_terminated_papi_file_path(
    tournament_ffe_id: int,
) -> Path:
    """Returns the path of the Papi file of the tournament, once the tournament is terminated."""
    return tmp_dir / f'{tournament_ffe_id}-terminated.papi'


def get_error_file_path(
    tournament_ffe_id: int,
) -> Path:
    """Returns the path of the error file of the tournament."""
    return tmp_dir / f'{tournament_ffe_id}.error'


def get_terminated_error_file_path(
    tournament_ffe_id: int,
) -> Path:
    """Returns the path of the error file of the tournament, once the tournament is terminated."""
    return tmp_dir / f'{tournament_ffe_id}-terminated.error'


def get_error(
    tournament_ffe_id: int,
) -> str | None:
    """Returns the error that has been found for the tournament, if any."""
    error_file_path: Path = get_terminated_error_file_path(tournament_ffe_id)
    if error_file_path.exists():
        with open(error_file_path, 'r') as f:
            return f.read()
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
    """Sets the error for the tournament."""
    with open(get_error_file_path(tournament_ffe_id), 'w') as f:
        f.write(error)
    print_interactive_warning(error)


def set_terminated_error(
    tournament_ffe_id: int,
    error: str,
) -> None:
    """Sets the error for the tournament, for terminated tournaments."""
    with open(get_terminated_error_file_path(tournament_ffe_id), 'w') as f:
        f.write(error)
    print_interactive_warning(error)


def download_papi_file_if_needed(
    tournament_ffe_id: int,
) -> bool:
    """Download the Papi file of the tournament, if needed only. Returns True on success, False otherwise."""
    terminated_papi_file_path: Path = get_terminated_papi_file_path(tournament_ffe_id)
    if terminated_papi_file_path.exists():
        return True
    papi_file_path: Path = get_papi_file_path(tournament_ffe_id)
    if papi_file_path.exists():
        if time() - papi_file_path.lstat().st_mtime > cache_tll:
            return True
        papi_file_path.unlink()
    try:
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
                set_error(tournament_ffe_id, f'Download HTTP exception: {he}')
            return False
    except BaseException as be:
        set_error(tournament_ffe_id, f'Download exception: {str(be)}')
        papi_file_path.unlink(missing_ok=True)
        return False


def get_event_uniq_id(
    tournament_ffe_id: int,
) -> str:
    """Returns the name of the event created to check the pairings."""
    return f'ffe-checker-{tournament_ffe_id}'


def create_event(
    tournament_ffe_id: int,
) -> Event | None:
    """Creates an event for the tournament to check the pairings.
    Returns the event on success, None on failure (when the Papi
    file could not be downloaded)."""
    event_uniq_id: str = get_event_uniq_id(tournament_ffe_id)
    try:
        event_loader = EventLoader()
        if event_uniq_id in event_loader.event_uniq_ids:
            return event_loader.load_event(event_uniq_id)
        if not download_papi_file_if_needed(tournament_ffe_id):
            return None
        print_interactive_info(f'Creating Sharly Chess event [{event_uniq_id}]...')
        EventDatabase(event_uniq_id).create()
        terminated_papi_file_path: Path = get_terminated_papi_file_path(
            tournament_ffe_id
        )
        papi_file_path: Path = (
            terminated_papi_file_path
            if terminated_papi_file_path.exists()
            else get_papi_file_path(tournament_ffe_id)
        )
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
    """Returns the path of the file used to store the results,
    in JSON format."""
    return tmp_dir / f'{tournament_ffe_id}.json'


def get_terminated_check_file_path(
    tournament_ffe_id: int,
) -> Path:
    """Returns the path of the file used to store the results,
    in JSON format, for terminated tournaments."""
    return tmp_dir / f'{tournament_ffe_id}-terminated.json'


def check_pairings_if_needed(
    tournament_ffe_id: int,
) -> TournamentCheck | None:
    """Create a SC event with the data of the FFE tournament
    and checks the pairings of the tournament, returns the
    check results or None on failure."""
    if error := get_error(tournament_ffe_id):
        print_interactive_warning(error)
        return None
    terminated_check_file_path: Path = get_terminated_check_file_path(tournament_ffe_id)
    if terminated_check_file_path.exists():
        return TournamentCheck.load_from_file(terminated_check_file_path)
    check_file_path: Path = get_check_file_path(tournament_ffe_id)
    if check_file_path.exists():
        if time() - check_file_path.lstat().st_mtime > cache_tll:
            return TournamentCheck.load_from_file(check_file_path)
        check_file_path.unlink()
    try:
        if event := create_event(tournament_ffe_id):
            tournament = list(event.tournaments)[0]
            if not tournament.finished:
                set_error(tournament_ffe_id, 'Tournament is not terminated.')
                EventDatabase(event.uniq_id).file.unlink()
                return None
            try:
                if get_papi_file_path(tournament_ffe_id).exists():
                    get_papi_file_path(tournament_ffe_id).replace(
                        get_terminated_papi_file_path(tournament_ffe_id)
                    )
                if tournament.player_count * 2 < tournament.rounds:
                    set_terminated_error(
                        tournament_ffe_id,
                        f'Not enough players ({tournament.player_count}) for {tournament.rounds} rounds.',
                    )
                    EventDatabase(event.uniq_id).file.unlink()
                    return None
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
                tournament_check.dump_to_file(
                    get_terminated_check_file_path(tournament_ffe_id)
                    if tournament.finished
                    else get_check_file_path(tournament_ffe_id)
                )
                EventDatabase(event.uniq_id).file.unlink()
                return tournament_check
            except BaseException as be:
                set_terminated_error(
                    tournament_ffe_id,
                    f'Exception while checking the pairings: {str(be)}.',
                )
                EventDatabase(event.uniq_id).file.unlink()
                return None
        else:
            return None
    except BaseException:
        check_file_path.unlink(missing_ok=True)
        raise


def print_tournament_checks(
    tournament_checks: list[TournamentCheck],
):
    """Prints a summary of all the checks passed."""
    print_interactive_info('====== SUMMARY ======')
    t_total: int = len(tournament_checks)
    print_interactive_info(f'- Tournaments tested                  : {t_total}')
    print_interactive_info(
        f'- Rounds per tournament (min/max/avg) : {min(tournament_check.rounds for tournament_check in tournament_checks)}/{max(tournament_check.rounds for tournament_check in tournament_checks)}/{sum(tournament_check.rounds for tournament_check in tournament_checks) / len(tournament_checks):.2f}'
    )
    print_interactive_info(
        f'- Players per tournament (min/max/avg): {min(tournament_check.player_count for tournament_check in tournament_checks)}/{max(tournament_check.player_count for tournament_check in tournament_checks)}/{sum(tournament_check.player_count for tournament_check in tournament_checks) / len(tournament_checks):.2f}'
    )
    t_ok: int = len(
        [
            tournament_check
            for tournament_check in tournament_checks
            if not tournament_check.diff
        ]
    )
    t_ko: int = t_total - t_ok
    t_ok_pc: float = t_ok / t_total * 100
    t_ko_pc: float = 100 - t_ok_pc
    t_ok: int = len(
        [
            tournament_check
            for tournament_check in tournament_checks
            if not tournament_check.diff
        ]
    )
    print_interactive_info(
        f'- Tournaments with correct pairings   : {t_ok} ({t_ok_pc:.2f}%)'
    )
    print_interactive_info(
        f'- Tournaments with incorrect pairings : {t_ko} ({t_ko_pc:.2f}%)'
    )
    r_total: int = sum(
        [tournament_check.rounds for tournament_check in tournament_checks]
    )
    print_interactive_info(f'- Rounds tested                       : {r_total}')
    r_ko: int = sum(
        len(tournament_check.diff) for tournament_check in tournament_checks
    )
    r_ok: int = r_total - r_ko
    r_ok_pc: float = r_ok / r_total * 100
    r_ko_pc: float = 100 - r_ok_pc
    print_interactive_info(
        f'- Rounds with correct pairings        : {r_ok} ({r_ok_pc:.2f}%)'
    )
    print_interactive_info(
        f'- Rounds with incorrect pairings      : {r_ko} ({r_ko_pc:.2f}%)'
    )


def main():
    """Runs the checks."""
    tournament_checks: list[TournamentCheck] = []
    for tournament_ffe_id in range(first_tournament_id, 0, -1):
        if (
            tournament_ffe_id
            not in [
                # 68724,  # 5 players, 15 rounds => KeyError
                # 68203,  # 2 players
                # 68202,  # 2 players
            ]
        ):
            print_interactive_info(f'Tournament #{tournament_ffe_id}:')
            if tournament_check := check_pairings_if_needed(tournament_ffe_id):
                tournament_check.print()
                tournament_checks.append(tournament_check)
                print_interactive_info(f'{len(tournament_checks)} tournaments checked.')
                if len(tournament_checks) == tournament_count:
                    break
                if len(tournament_checks) % 100 == 0:
                    print_tournament_checks(tournament_checks)
    print_tournament_checks(tournament_checks)


if __name__ == '__main__':
    main()
