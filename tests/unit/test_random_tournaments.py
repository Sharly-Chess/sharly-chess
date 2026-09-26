"""The random tournament generator.

The check-list requires one (C.04.A Annex 3, question 19), lists what it
must let the user vary (question 24), asks that it not answer the same
twice unless asked to (question 30), and that what it writes have
"correct pairings and standings" (question 31).
"""

import collections
import random
from pathlib import Path

import pytest

from data.pairings.random_tournaments import (
    MANDATORY_INDIVIDUAL_TIE_BREAKS,
    MANDATORY_TEAM_TIE_BREAKS,
    Frequency,
    TournamentSettings,
    generate_tournament_file,
)


def _result_codes(trf_path: Path) -> collections.Counter:
    """Every round's result letter, over all players."""
    codes: collections.Counter = collections.Counter()
    for line in trf_path.read_text(encoding='ascii').splitlines():
        if not line.startswith('001'):
            continue
        for start in range(91, len(line), 10):
            field = line[start : start + 8]
            if len(field) == 8:
                codes[field[7]] += 1
    return codes


@pytest.mark.unit
@pytest.mark.parametrize(
    ('written', 'expected'),
    [
        ('4', Frequency(count=4)),
        ('5%', Frequency(rate=0.05)),
        ('0.05', Frequency(rate=0.05)),
        ('0', Frequency(count=0)),
        (None, None),
    ],
)
def test_a_frequency_is_a_number_or_a_percentage(written, expected):
    assert Frequency.parse(written) == expected


@pytest.mark.unit
def test_a_fixed_number_of_byes_is_the_number_written(tmp_path: Path):
    """Question 24 asks for each kind to be settable as a fixed number."""
    trf_path = tmp_path / 'counted.trf'
    generate_tournament_file(
        TournamentSettings(
            players=30,
            rounds=9,
            half_point_byes=Frequency(count=6),
            zero_point_byes=Frequency(count=3),
            full_point_byes=Frequency(count=0),
            forfeit_wins=Frequency(count=0),
            forfeit_losses=Frequency(count=0),
            unusual_results=Frequency(count=0),
        ),
        trf_path,
        seed=77,
    )
    codes = _result_codes(trf_path)
    assert codes['H'] == 6
    assert codes['Z'] == 3
    assert codes['F'] == 0
    # A forfeited board shows as a loss for one side and a win for the
    # other, so asking for none of either leaves both out.
    assert codes['+'] == 0
    assert codes['-'] == 0


@pytest.mark.unit
def test_a_forfeit_takes_both_sides_of_one_board(tmp_path: Path):
    trf_path = tmp_path / 'forfeits.trf'
    generate_tournament_file(
        TournamentSettings(
            players=20,
            rounds=5,
            full_point_byes=Frequency(count=0),
            half_point_byes=Frequency(count=0),
            zero_point_byes=Frequency(count=0),
            forfeit_wins=Frequency(count=0),
            forfeit_losses=Frequency(count=3),
            unusual_results=Frequency(count=0),
        ),
        trf_path,
        seed=21,
    )
    codes = _result_codes(trf_path)
    assert codes['-'] == 3
    assert codes['+'] == 3


@pytest.mark.unit
def test_the_same_seed_gives_the_same_tournament(tmp_path: Path):
    """Question 30: reproducible when a seed is given."""
    settings = TournamentSettings(players=16, rounds=5)
    first, second = tmp_path / 'a.trf', tmp_path / 'b.trf'
    generate_tournament_file(settings, first, seed=99)
    generate_tournament_file(settings, second, seed=99)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.unit
def test_without_a_seed_the_tournament_differs(tmp_path: Path):
    """Question 30: 'The generation is not random if the THP's RTG always
    produces the same TRF report when invoked with the same configurable
    parameters.'"""
    settings = TournamentSettings(players=16, rounds=5)
    first, second = tmp_path / 'c.trf', tmp_path / 'd.trf'
    generate_tournament_file(settings, first)
    generate_tournament_file(settings, second)
    assert first.read_bytes() != second.read_bytes()


@pytest.mark.unit
def test_the_file_states_the_tie_breaks_it_was_ranked_on(tmp_path: Path):
    """Question 31 asks the standings to be those of the tie-break list
    the report names, which means the report has to name one."""
    trf_path = tmp_path / 'ranked.trf'
    generate_tournament_file(
        TournamentSettings(players=18, rounds=5, tie_breaks=['PTS', 'BH/C1', 'SB']),
        trf_path,
        seed=5,
    )
    declared = [
        line
        for line in trf_path.read_text(encoding='ascii').splitlines()
        if line.startswith('212')
    ]
    assert declared == ['212 PTS,BH/C1,SB']


@pytest.mark.unit
def test_the_pairings_and_standings_are_its_own(tmp_path: Path):
    """Question 31, checked by the checker of question 21."""
    from data.input_output.trf.trf_serializer import TrfSerializer
    from data.loader import EventLoader
    from data.pairings.checkers import check_standings

    trf_path = tmp_path / 'checked.trf'
    generate_tournament_file(
        TournamentSettings(players=22, rounds=7, tie_breaks=['PTS', 'BH/C1', 'SB']),
        trf_path,
        seed=31,
    )
    from data.input_output.tournament_importer_options import FileOption
    from data.input_output.trf.trf_importer import TrfTournamentImporter
    from database.sqlite.event.event_database import EventDatabase
    from tests.test_config import TestUtils

    uniq_id = 'test-generated-check'
    TestUtils.create_event(uniq_id)
    try:
        tournament_id = TrfTournamentImporter([FileOption(trf_path)]).load_tournament(
            EventLoader().load_event(uniq_id)
        )
        EventLoader.unload_event(uniq_id)
        event = EventLoader().load_event(uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        engine = tournament.pairing_variation.engine
        for round_ in range(1, tournament.current_round + 1):
            assert not engine.pairings_diff(tournament, round_, ignore_order=True), (
                f'round {round_} is not the pairing our own engine makes'
            )
        with open(trf_path, encoding='ascii') as file:
            trf_tournament = TrfSerializer.load(file)
        diffs, unapplied, criteria, _round = check_standings(
            tournament, trf_tournament, event
        )
        assert unapplied == []
        assert criteria == ['PTS', 'BH/C1', 'SB']
        assert diffs == []
    finally:
        EventDatabase(uniq_id).delete()


@pytest.mark.unit
def test_a_team_event_generates_a_team_tournament(tmp_path: Path):
    """Asked for teams, the generator builds a team Swiss: the teams are the
    field, the players fill their boards, and the file carries the team
    records."""
    trf_path = tmp_path / 'teams.trf'
    generate_tournament_file(
        TournamentSettings(teams=8, players_per_team=4, rounds=5),
        trf_path,
        seed=17,
    )
    lines = trf_path.read_text(encoding='ascii').splitlines()
    players = [line for line in lines if line.startswith('001')]
    rosters = [line for line in lines if line.startswith('310')]
    assert len(players) == 32
    assert len(rosters) == 8, 'one 310 roster per team'
    assert any(line.startswith('192') for line in lines), 'the encoded type'


@pytest.mark.unit
def test_a_team_forfeit_takes_one_board_of_one_match(tmp_path: Path):
    trf_path = tmp_path / 'team-forfeits.trf'
    generate_tournament_file(
        TournamentSettings(
            teams=8,
            players_per_team=4,
            rounds=5,
            full_point_byes=Frequency(count=0),
            half_point_byes=Frequency(count=0),
            zero_point_byes=Frequency(count=0),
            forfeit_wins=Frequency(count=0),
            forfeit_losses=Frequency(count=3),
            unusual_results=Frequency(count=0),
        ),
        trf_path,
        seed=21,
    )
    codes = _result_codes(trf_path)
    assert codes['-'] == 3
    assert codes['+'] == 3


@pytest.mark.unit
def test_a_team_tournament_keeps_two_teams_to_pair(tmp_path: Path):
    """Byes are the team's, so a rate high enough to empty the round has to
    be held back: an engine given fewer than two teams has nothing to pair."""
    trf_path = tmp_path / 'byes.trf'
    generate_tournament_file(
        TournamentSettings(
            teams=4,
            players_per_team=2,
            rounds=3,
            full_point_byes=Frequency(rate=1.0),
            half_point_byes=Frequency(rate=1.0),
        ),
        trf_path,
        seed=23,
    )
    assert trf_path.exists()


@pytest.mark.unit
def test_the_rounds_can_be_left_unpaired(tmp_path: Path):
    """The field entered and nothing else, for a tournament that is going to
    be paired by hand."""
    trf_path = tmp_path / 'unpaired.trf'
    generate_tournament_file(
        TournamentSettings(players=12, rounds=5, pair_rounds=False),
        trf_path,
        seed=5,
    )
    players = [
        line
        for line in trf_path.read_text(encoding='ascii').splitlines()
        if line.startswith('001')
    ]
    assert len(players) == 12
    # 001 carries a round's game from column 92 on; there are none.
    assert all(not line[91:].strip() for line in players)


@pytest.mark.unit
@pytest.mark.parametrize('pair_rounds', [True, False])
def test_generating_twice_into_one_event_names_them_apart(pair_rounds: bool):
    """An event holds one tournament of a given name, and generating into one
    that already holds a generated tournament is the ordinary case."""
    from data.loader import EventLoader
    from data.pairings.random_tournaments import RandomTournamentGenerator
    from database.sqlite.event.event_database import EventDatabase
    from tests.test_config import TestUtils

    uniq_id = f'test-generated-twice-{pair_rounds}'
    TestUtils.create_event(uniq_id)
    try:
        settings = TournamentSettings(
            players=8, rounds=2, pair_rounds=pair_rounds, name='Generated tournament'
        )
        generator = RandomTournamentGenerator(3)
        generator.generate(settings, uniq_id)
        generator.generate(settings, uniq_id)
        EventLoader.unload_event(uniq_id)
        names = sorted(
            tournament.name
            for tournament in EventLoader().load_event(uniq_id).tournaments
        )
        assert names == ['Generated tournament', 'Generated tournament (2)']
    finally:
        EventDatabase(uniq_id).delete()


@pytest.mark.unit
def test_a_tournament_that_cannot_be_finished_is_not_generated():
    """Six players over five rounds, with no byes or forfeits, is nearly a
    round robin, and this draw runs out of legal pairings before the end:
    the tournament is refused, and the event it was generated into is left
    without it."""
    from data.loader import EventLoader
    from data.pairings.random_tournaments import (
        RandomTournamentGenerator,
        UnfinishedTournament,
    )
    from database.sqlite.event.event_database import EventDatabase
    from tests.test_config import TestUtils

    uniq_id = 'test-generated-unfinished'
    TestUtils.create_event(uniq_id)
    try:
        none = Frequency(count=0)
        settings = TournamentSettings(
            players=6,
            rounds=5,
            full_point_byes=none,
            half_point_byes=none,
            zero_point_byes=none,
            forfeit_wins=none,
            forfeit_losses=none,
            unusual_results=none,
            acceleration=False,
            tie_breaks=['PTS'],
        )
        with pytest.raises(UnfinishedTournament):
            RandomTournamentGenerator(1).generate(settings, uniq_id)
        EventLoader.unload_event(uniq_id)
        assert not list(EventLoader().load_event(uniq_id).tournaments)
    finally:
        EventDatabase(uniq_id).delete()


@pytest.mark.unit
def test_a_team_file_states_the_initial_colour_its_first_round_was_paired_with(
    tmp_path: Path,
):
    """C.04.6 art. 4.3.1 gives the first-team of a round-1 match the
    initial-colour when its TPN is odd and the opposite colour when it is
    even, so record 152 read back from round 1 must invert the colour of a
    first-team with an even TPN. In this tournament team 1 sits out round 1,
    and the top match is team 2's."""
    trf_path = tmp_path / 'team.trf'
    generate_tournament_file(
        TournamentSettings(tie_breaks=['PTS', 'SSSC'], team_event=True),
        trf_path,
        2542,
    )
    lines = trf_path.read_text(encoding='ascii').splitlines()
    # 310: number, name, federation, MP, GP, rank, then the members.
    members = {
        int(line.split()[1]): [int(number) for number in line.split()[8:]]
        for line in lines
        if line.startswith('310')
    }
    round_one = {}
    for line in lines:
        if line.startswith('001') and line[91:95].strip() not in ('', '0000'):
            round_one[int(line[4:8])] = (int(line[91:95]), line[96])
    board_one = {numbers[0]: team for team, numbers in members.items()}
    first_team = min(team for player, team in board_one.items() if player in round_one)
    assert first_team % 2 == 0
    colour = round_one[members[first_team][0]][1]
    initial = {'w': 'W', 'b': 'B'}[colour]
    initial = {'W': 'B', 'B': 'W'}[initial]
    assert next(line for line in lines if line.startswith('152')) == f'152 {initial}'


@pytest.mark.unit
def test_teams_level_on_every_criterion_share_the_rank(tmp_path: Path):
    """The rank field of a 310 record allows ties, and teams the criteria
    leave level are level (C.07 Art. 4.2), as the individual rank field
    already says. Ranked on match points alone, every team on the same
    total shares the rank the standings reached it at."""
    trf_path = tmp_path / 'teams.trf'
    generate_tournament_file(
        TournamentSettings(teams=10, players_per_team=2, rounds=5, tie_breaks=['PTS']),
        trf_path,
        seed=23,
    )
    by_rank: dict[int, list[float]] = {}
    for line in trf_path.read_text(encoding='ascii').splitlines():
        if not line.startswith('310'):
            continue
        if not line[68:71].strip():
            continue
        match_points = float(line[54:60])
        by_rank.setdefault(int(line[68:71]), []).append(match_points)

    assert len(by_rank) > 1, 'the field is not all level'
    for rank, totals in by_rank.items():
        assert len(set(totals)) == 1, (
            f'rank {rank} holds teams on different match points: {totals}'
        )
    # A rank is the position the first team of its group reached, so the
    # ranks are the running count of the teams above each group.
    seen = 0
    for rank in sorted(by_rank):
        assert rank == seen + 1, f'rank {rank} does not follow {seen} teams'
        seen += len(by_rank[rank])


@pytest.mark.unit
def test_a_team_run_varies_the_colour_rule_and_the_scores(tmp_path: Path):
    """The 192 encoded type carries three choices a team competition makes —
    the colour-preference rule of art. 1.7, which score is primary, and
    whether the secondary score decides the colour allocation of art. 4.2.2.
    A run that states none of them draws each per tournament, so the cross-
    check exercises Type B and a game-point primary as well as the defaults."""
    codes = set()
    for seed in range(1, 13):
        trf_path = tmp_path / f'teams-{seed}.trf'
        generate_tournament_file(
            TournamentSettings(teams=6, players_per_team=2, rounds=3),
            trf_path,
            seed=seed,
        )
        codes |= {
            line.split(' ', 1)[1].strip()
            for line in trf_path.read_text(encoding='ascii').splitlines()
            if line.startswith('192')
        }
    assert any('TYPEA' in code for code in codes), codes
    assert any('TYPEB' in code for code in codes), codes
    assert any(not code.startswith('FIDE_TEAM_TYPE') for code in codes), codes
    assert any(code.endswith('_GP') for code in codes), codes


@pytest.mark.unit
def test_an_unstated_tie_break_list_and_acceleration_are_drawn():
    """Question 25: "always using the same fixed values is not acceptable"
    for a parameter the user leaves out, the tie-break list and the Baku
    acceleration among them."""
    settled = [TournamentSettings().settled(random.Random(seed)) for seed in range(40)]
    lists = {tuple(settings.tie_breaks or ()) for settings in settled}
    assert len(lists) > 1
    assert all(
        tie_breaks[0] == 'PTS'
        and set(tie_breaks[1:]) <= set(MANDATORY_INDIVIDUAL_TIE_BREAKS)
        for tie_breaks in lists
    )
    assert {settings.acceleration for settings in settled} == {True, False}


@pytest.mark.unit
def test_a_team_run_draws_team_tie_breaks_and_no_acceleration():
    settled = [
        TournamentSettings().settled(random.Random(seed), team_event=True)
        for seed in range(20)
    ]
    assert all(settings.acceleration is False for settings in settled)
    assert all(
        set((settings.tie_breaks or [])[1:]) <= set(MANDATORY_TEAM_TIE_BREAKS)
        for settings in settled
    )


@pytest.mark.unit
def test_a_stated_tie_break_list_and_acceleration_are_kept():
    settings = TournamentSettings(tie_breaks=['PTS', 'SB'], acceleration=False)
    for seed in range(10):
        settled = settings.settled(random.Random(seed))
        assert settled.tie_breaks == ['PTS', 'SB']
        assert settled.acceleration is False
