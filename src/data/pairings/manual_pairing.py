"""The checks made while an arbiter pairs a round by hand in FIDE mode: the
absolute criteria a pairing may break, and the comparison of the round with
the pairing engine's."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from common.exception import SharlyChessException
from common.i18n import _
from utils.enum import BoardColor, Result

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.teams.team import Team
    from data.tournament import Tournament

type RoundPairs = set[tuple[int, int | None]]
"""The pairs of a round, first (white) member then second (black) one, by
player id — team id in a team tournament; ``None`` for the pairing-allocated
bye."""


def played_colours(player: 'TournamentPlayer', before_round: int) -> list[BoardColor]:
    """The colours *player* had in the games actually played (or still to be
    played) before *before_round*: byes and forfeits have no colour."""
    colours: list[BoardColor] = []
    for round_ in range(1, before_round):
        pairing = player.pairings_by_round.get(round_)
        if (
            pairing is None
            or pairing.opponent is None
            or pairing.result.is_forfeit
            or (colour := pairing.color) is None
        ):
            continue
        colours.append(colour)
    return colours


def colour_preference(player: 'TournamentPlayer', round_: int) -> BoardColor | None:
    """The colour *player* should get in *round_* (FIDE C.04.3 A.6): the one
    they had less of, or the opposite of the last one when even; none before
    their first game."""
    colours = played_colours(player, round_)
    if not colours:
        return None
    difference = colours.count(BoardColor.WHITE) - colours.count(BoardColor.BLACK)
    if difference > 0:
        return BoardColor.BLACK
    if difference < 0:
        return BoardColor.WHITE
    return _opposite(colours[-1])


def _opposite(colour: BoardColor) -> BoardColor:
    return BoardColor.BLACK if colour == BoardColor.WHITE else BoardColor.WHITE


def _colour_violation(
    tournament: 'Tournament',
    round_: int,
    player: 'TournamentPlayer',
    colour: BoardColor,
) -> str | None:
    if round_ >= tournament.rounds:
        return None
    colours = [*played_colours(player, round_), colour]
    if colours[-3:] == [colour] * 3:
        return _('[{player}] would play {colour} for the third time in a row.').format(
            player=player.full_name, colour=_colour_name(colour)
        )
    difference = colours.count(BoardColor.WHITE) - colours.count(BoardColor.BLACK)
    if abs(difference) > 2:
        return _('[{player}] would have a colour difference of {difference}.').format(
            player=player.full_name, difference=f'{difference:+d}'
        )
    return None


def _colour_name(colour: BoardColor) -> str:
    return _('White') if colour == BoardColor.WHITE else _('Black')


def _have_played(
    first: 'TournamentPlayer', second: 'TournamentPlayer', before_round: int
) -> bool:
    return any(
        (pairing := first.pairings_by_round.get(round_)) is not None
        and pairing.played
        and pairing.opponent_id == second.id
        for round_ in range(1, before_round)
    )


def _prohibited(
    tournament: 'Tournament', round_: int, first_id: int, second_id: int
) -> bool:
    prohibited_pairings = tournament.prohibited_pairings
    groups = [group.member_ids for group in prohibited_pairings.snapshot(round_)] or [
        member_ids
        for _is_hard, member_ids in prohibited_pairings.computed_groups(round_)
    ]
    return any(first_id in group and second_id in group for group in groups)


def pairing_violations(
    tournament: 'Tournament',
    round_: int,
    white: 'TournamentPlayer',
    black: 'TournamentPlayer',
) -> list[str]:
    """The absolute criteria pairing *white* against *black* in *round_*
    would break."""
    violations: list[str] = []
    if _have_played(white, black, round_):
        violations.append(
            _('[{white}] and [{black}] have already played each other.').format(
                white=white.full_name, black=black.full_name
            )
        )
    if _prohibited(tournament, round_, white.id, black.id):
        violations.append(
            _('[{white}] and [{black}] must not be paired together.').format(
                white=white.full_name, black=black.full_name
            )
        )
    violations.extend(colour_violations(tournament, round_, white, black))
    return violations


def colour_violations(
    tournament: 'Tournament',
    round_: int,
    white: 'TournamentPlayer',
    black: 'TournamentPlayer',
) -> list[str]:
    """The colour criteria giving *white* white and *black* black in
    *round_* would break: three colours in a row, or a colour difference
    above two, before the last round."""
    return [
        violation
        for player, colour in ((white, BoardColor.WHITE), (black, BoardColor.BLACK))
        if (violation := _colour_violation(tournament, round_, player, colour))
    ]


def bye_violations(
    tournament: 'Tournament', round_: int, player: 'TournamentPlayer'
) -> list[str]:
    """Why *player* should not get the pairing-allocated bye of *round_*: a
    player gets it once, and not after a win by forfeit or a full-point bye
    (FIDE C.04.1.d), and it goes to the lowest score."""
    violations = bye_eligibility_violations(player, round_)
    score = _score(player, round_)
    if any(
        _score(other, round_) < score
        for other in tournament.tournament_players
        if other.id != player.id
        and (pairing := other.pairings_by_round.get(round_)) is not None
        and pairing.board is not None
        and not _had_bye_or_forfeit_win(other, round_)
    ):
        violations.append(
            _(
                '[{player}] gets the pairing-allocated bye although other '
                'players who could have it have a lower score.'
            ).format(player=player.full_name)
        )
    return violations


def bye_eligibility_violations(player: 'TournamentPlayer', round_: int) -> list[str]:
    """Why *player* cannot have the pairing-allocated bye of *round_* at all,
    whoever else is paired."""
    if not _had_bye_or_forfeit_win(player, round_):
        return []
    return [
        _(
            '[{player}] has already had a pairing-allocated bye, '
            'a win by forfeit or a full-point bye.'
        ).format(player=player.full_name)
    ]


def _had_bye_or_forfeit_win(player: 'TournamentPlayer', round_: int) -> bool:
    """Whether *player* can no longer get the pairing-allocated bye, having
    had it, a win by forfeit or a full-point bye before *round_*."""
    return any(
        (pairing := player.pairings_by_round.get(round_before)) is not None
        and pairing.result
        in (Result.PAIRING_ALLOCATED_BYE, Result.FORFEIT_WIN, Result.FULL_POINT_BYE)
        for round_before in range(1, round_)
    )


def _score(player: 'TournamentPlayer', round_: int) -> float:
    return sum(
        pairing.points
        for round_before in range(1, round_)
        if (pairing := player.pairings_by_round.get(round_before)) is not None
    )


def both_against_preference(
    round_: int, white: 'TournamentPlayer', black: 'TournamentPlayer'
) -> bool:
    """Whether both players get the colour opposite to the one they should
    have."""
    return colour_preference(white, round_) == BoardColor.BLACK and (
        colour_preference(black, round_) == BoardColor.WHITE
    )


def team_pairing_violations(
    tournament: 'Tournament', round_: int, first: 'Team', second: 'Team'
) -> list[str]:
    """The absolute criteria pairing team *first* against *second* in
    *round_* would break."""
    violations: list[str] = []
    if any(
        {team_board.stored_team_board.team_a_id, team_board.stored_team_board.team_b_id}
        == {first.id, second.id}
        for round_before in range(1, round_)
        for team_board in tournament.get_round_team_boards(round_before)
    ):
        violations.append(
            _('[{first}] and [{second}] have already played each other.').format(
                first=first.name, second=second.name
            )
        )
    if _prohibited(tournament, round_, first.id, second.id):
        violations.append(
            _('[{first}] and [{second}] must not be paired together.').format(
                first=first.name, second=second.name
            )
        )
    return violations


def _team_paired(tournament: 'Tournament') -> bool:
    return tournament.is_team_tournament and tournament.pairing_system.paired_by_team


def round_pairs(tournament: 'Tournament', round_: int) -> RoundPairs:
    """The pairs the arbiter made for *round_*, leaving out the byes they
    gave by hand."""
    if _team_paired(tournament):
        return {
            (
                team_board.stored_team_board.team_a_id,
                team_board.stored_team_board.team_b_id,
            )
            for team_board in tournament.get_round_team_boards(round_)
            if team_board.bye_type in (None, 'PAB')
        }
    return {
        (board.stored_board.white_player_id, board.stored_board.black_player_id)
        for board in tournament.get_round_boards(round_)
        if board.stored_board.white_player_id is not None
    }


def changed_pairs(
    start: RoundPairs | None, actual: RoundPairs, pairs: RoundPairs
) -> RoundPairs:
    """Those of *pairs* involving a member whose pairing changed between
    *start* and *actual*: the manual pairing is answerable for them, not for
    the rest of the round. All of them when *start* is not known."""
    if start is None:
        return pairs
    changed = {member for pair in start ^ actual for member in pair}
    return {pair for pair in pairs if changed.intersection(pair)}


def differing_pairs(
    start: RoundPairs | None, actual: RoundPairs, expected: RoundPairs
) -> tuple[RoundPairs, RoundPairs]:
    """The pairs of *expected* missing from *actual*, and those of *actual*
    it does not expect, that the change from *start* to *actual* accounts
    for: the ones of the members moved, then of the members they now meet
    or should meet, and so on, so that both sides name the same members.
    All of them when *start* is not known."""
    missing, extra = expected - actual, actual - expected
    if start is None:
        return missing, extra
    members = {
        member for pair in start ^ actual for member in pair if member is not None
    }
    while True:
        involved = {pair for pair in missing | extra if members.intersection(pair)}
        reached = members | {
            member for pair in involved for member in pair if member is not None
        }
        if reached == members:
            return missing & involved, extra & involved
        members = reached


def describe_pairs(tournament: 'Tournament', pairs: RoundPairs) -> str:
    """*pairs* in pairing numbers, as in the TRF comments: ``'19-7 44=PAB'``."""
    number = _pairing_number_reader(tournament)
    return ' '.join(
        sorted(
            (
                f'{number(first)}=PAB'
                if second is None
                else f'{number(first)}-{number(second)}'
            )
            for first, second in pairs
        )
    )


def _pairing_number_reader(tournament: 'Tournament') -> Callable[[int], int]:
    if _team_paired(tournament):
        teams = tournament.event.teams_by_id
        return lambda id_: teams[id_].pairing_number or 0
    players = tournament.tournament_players_by_id
    return lambda id_: players[id_].pairing_number or 0


def pair_labels(tournament: 'Tournament', pairs: RoundPairs) -> list[str]:
    """*pairs* as the arbiter reads them, each member's name followed by
    their pairing number, in the order of the first member's pairing
    number."""
    number = _pairing_number_reader(tournament)
    if _team_paired(tournament):
        teams = tournament.event.teams_by_id

        def name(id_: int) -> str:
            return f'{teams[id_].name} ({number(id_)})'
    else:
        players = tournament.tournament_players_by_id

        def name(id_: int) -> str:
            return f'{players[id_].full_name} ({number(id_)})'

    return [
        (
            _('{first} — Pairing-Allocated Bye').format(first=name(first))
            if second is None
            else f'{name(first)} — {name(second)}'
        )
        for first, second in sorted(pairs, key=lambda pair: number(pair[0]))
    ]


def rounds_change_breach(
    tournament: 'Tournament', rounds: int
) -> tuple[RoundPairs, RoundPairs] | None:
    """What playing *rounds* rounds instead of the current count does to the
    last paired round, which is paired differently when it becomes, or stops
    being, the last round: the engine's pairs and the round's that differ
    because of it. ``None`` when nothing changes, or when the engine
    cannot tell."""
    round_ = tournament.last_paired_round
    if not round_ or (round_ == tournament.rounds) == (round_ == rounds):
        return None
    engine = tournament.pairing_variation.engine
    stored_tournament = tournament.stored_tournament
    current_rounds = stored_tournament.rounds
    try:
        before = engine.expected_round_pairs(tournament, round_)
        stored_tournament.rounds = rounds
        after = engine.expected_round_pairs(tournament, round_)
    except SharlyChessException:
        return None
    finally:
        stored_tournament.rounds = current_rounds
    actual = round_pairs(tournament, round_)
    missing, extra = differing_pairs(before, after, actual)
    if not (missing or extra):
        return None
    return missing, extra


def imported_round_breaches(
    tournament: 'Tournament',
) -> list[tuple[int, RoundPairs, RoundPairs]]:
    """The rounds of a tournament just imported whose pairings are not the
    engine's, each with the engine's pairs and the imported ones that
    differ. A round the engine cannot pair is left out."""
    engine = tournament.pairing_variation.engine
    breaches: list[tuple[int, RoundPairs, RoundPairs]] = []
    for round_ in range(1, tournament.last_paired_round + 1):
        if not tournament.round_has_pairings(round_):
            continue
        try:
            expected = engine.expected_round_pairs(
                tournament, round_, stored_prohibitions=True
            )
        except SharlyChessException:
            continue
        actual = round_pairs(tournament, round_)
        if (missing := expected - actual) | (extra := actual - expected):
            breaches.append((round_, missing, extra))
    return breaches
