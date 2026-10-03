"""Build a team event whose tournament is reported to FIDE in slices.

An interclubs season runs from autumn to spring, one round a month, and
is registered with the federation one slice at a time — the case
<https://ratings.fide.com/tournament_src_report.phtml?code=441469> is a
single round of one. A team file names its teams and their rosters as
well as its players, so testing a slice of one needs teams, boards and a
rating per slice.

The rounds are laid out around today, so the season is always under way
and the slices before the current one hold ratings of their own.
"""

import random
import sys
from argparse import ArgumentParser

from utils.scripts import init_script

arguments = init_script()

from common.logger import (  # Noqa: E402
    print_interactive_error,
    print_interactive_info,
    print_interactive_success,
)
from database.sqlite.event.event_database import EventDatabase  # Noqa: E402
from database.sqlite.event.event_store import (  # Noqa: E402
    StoredEvent,
    StoredPlayerPeriod,
    StoredTeam,
    StoredTournament,
    StoredTournamentPlayer,
)
from multi_period_players import (  # Noqa: E402
    build_player,
    parse_period_first_rounds,
    period_lines,
    round_datetime,
)
from utils.enum import EventType, PlayerRatingType, TournamentRating  # Noqa: E402

CLUBS = [
    'Rennes',
    'Brest',
    'Quimper',
    'Lorient',
    'Vannes',
    'Saint-Brieuc',
    'Saint-Malo',
    'Fougères',
]


def generate(
    uniq_id: str,
    rounds: int,
    period_first_rounds: list[int],
    team_count: int,
    board_count: int,
    substitutes: int,
    interval: int,
    seed: int,
) -> None:
    generator = random.Random(seed)
    database = EventDatabase(uniq_id)
    if database.file.exists():
        print_interactive_error(f'Event [{uniq_id}] already exists.')
        sys.exit(1)
    database.create()

    round_datetimes = {
        round_nb: round_datetime(round_nb, rounds, interval)
        for round_nb in range(1, rounds + 1)
    }
    roster_size = board_count + substitutes
    with EventDatabase(uniq_id, write=True) as event_database:
        event_database.update_stored_event(
            StoredEvent(
                uniq_id=uniq_id,
                name=f'Multi-period team test ({uniq_id})',
                federation='FRA',
                player_rating_type=PlayerRatingType.FIDE.value,
                location='Rennes',
                public=True,
                event_type=EventType.TEAM,
                # The FFE is the federation that reports in slices, so the
                # event it is tested with has its plugin on.
                enabled_plugins=['ffe'],
            )
        )
        tournament_id = event_database.add_stored_tournament(
            StoredTournament(
                id=None,
                name='Interclubs en tranches',
                rounds=rounds,
                rating=TournamentRating.STANDARD.value,
                pairing='TEAM_SWISS_STANDARD',
                team_player_count=board_count,
                multi_period=True,
                start_date=round_datetimes[1].date(),
                stop_date=round_datetimes[rounds].date(),
                round_datetimes=dict(round_datetimes),
            )
        )
        event_database.set_tournament_periods(tournament_id, period_first_rounds)
        period_ids = [
            stored_period.id
            for stored_period in event_database.load_tournament_stored_periods(
                tournament_id
            )
        ]
        index = 0
        for team_index in range(team_count):
            team_id = event_database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'{CLUBS[team_index % len(CLUBS)]} '
                    f'{chr(ord("A") + team_index // len(CLUBS))}',
                    tournament_id=tournament_id,
                    pairing_number=team_index + 1,
                    check_in=True,
                )
            )
            for board in range(roster_size):
                stored_player, period_ratings = build_player(
                    index, len(period_ids), generator
                )
                stored_player.team_id = team_id
                stored_player.team_index = board + 1
                stored_player.check_in = True
                player_id = event_database.add_stored_player(stored_player)
                event_database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
                for period_id, ratings in zip(
                    period_ids[1:], period_ratings, strict=True
                ):
                    assert period_id is not None
                    event_database.set_player_period(
                        player_id,
                        period_id,
                        StoredPlayerPeriod(
                            ratings=ratings,
                            title=stored_player.title,
                            women_title=stored_player.women_title,
                        ),
                    )
                index += 1

    print_interactive_success(f'Event [{uniq_id}] has been created.')
    print_interactive_info(
        f'{team_count} teams of {roster_size} players '
        f'({board_count} boards) over {rounds} rounds:'
    )
    for line in period_lines(period_first_rounds, rounds, round_datetimes):
        print_interactive_info(line)


if __name__ == '__main__':
    parser = ArgumentParser(
        description='Command creating a team event to test tournaments reported '
        'in slices of at most 30 days.'
    )
    parser.add_argument(
        '-e',
        '--event',
        type=str,
        default='multi-period-teams',
        help='ID of the event to create (default: multi-period-teams).',
    )
    parser.add_argument(
        '-r',
        '--rounds',
        type=int,
        default=7,
        help='Number of rounds (default: 7).',
    )
    parser.add_argument(
        '-b',
        '--boundaries',
        type=int,
        nargs='+',
        default=[4, 6],
        help='Rounds starting a period, round 1 aside (default: 4 6).',
    )
    parser.add_argument(
        '-t',
        '--teams',
        type=int,
        default=8,
        # Eight teams pair seven rounds without anyone meeting twice, which
        # is the default number of rounds.
        help='Number of teams (default: 8).',
    )
    parser.add_argument(
        '-c',
        '--boards',
        type=int,
        default=4,
        help='Number of boards per team (default: 4).',
    )
    parser.add_argument(
        '-x',
        '--substitutes',
        type=int,
        default=1,
        help='Roster players beyond the boards (default: 1).',
    )
    parser.add_argument(
        '-i',
        '--interval',
        type=int,
        default=14,
        help='Days between two rounds (default: 14).',
    )
    parser.add_argument(
        '-s',
        '--seed',
        type=int,
        default=1,
        help='Seed of the ratings drawn (default: 1).',
    )
    args = parser.parse_args(arguments)
    generate(
        args.event,
        args.rounds,
        parse_period_first_rounds(args.boundaries, args.rounds),
        args.teams,
        args.boards,
        args.substitutes,
        args.interval,
        args.seed,
    )
