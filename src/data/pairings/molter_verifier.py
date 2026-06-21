"""Verifier for Molter pairing tables.

Checks a :class:`FixedPairingTable` against the principles of the Molter
team-pairing system. The principles split into two groups:

**Hard invariants** — must hold for *every* valid Molter table, whatever
the round count: even players-per-team and board count = teams × P/2;
one game per player per round (and equal games overall); no team-mates
paired; no player meeting two opponents from the same team (so rounds <
teams); exact per-team colour balance (possible because P is even); and
the floater rules — for an even team count no floaters at all (S6a), and
for an odd team count floaters only between consecutive boards with the
odd board descending, at most one per odd board level per round (S6b);
and the colour rules — over the regular rounds each player is
colour-balanced and never plays one colour three rounds running, and a
colour only repeats across an even→odd round boundary.

**Ideals** — reached only on the *complete* tables; the reduced
1/2/3-round tables cannot, so they are reported as notes rather
than errors: uniform team-vs-team distribution (principle 3), balanced
up/down floaters (principle 5), an equal count of descending floaters
per team (a priority ideal), even per-round opponent spread (principle
1), and per-player colour balance.

``verify_molter_table`` returns a :class:`MolterReport`; ``errors`` lists
hard-invariant breaches (non-empty ⇒ invalid), ``notes`` lists unmet
ideals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.pairings.fixed_table import FixedPairingTable, TablePairing


@dataclass
class MolterReport:
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_rounds(
    rounds: tuple[tuple['TablePairing', ...], ...],
    team_count: int,
    players_per_team: int,
    label: str,
    report: MolterReport,
) -> None:
    err = report.errors.append
    note = report.notes.append
    letters = tuple(chr(ord('A') + i) for i in range(team_count))
    team_by_letter = {letter: index for index, letter in enumerate(letters)}
    expected_boards = team_count * players_per_team // 2

    # The verifier may scan tens of thousands of generated boards in tests and
    # diagnostics. Keep this hot path flat-array and bitmask based: a more
    # idiomatic Counter/list-heavy version made large verification measurably slow.
    seat_count = team_count * players_per_team
    games = [0] * seat_count
    white_count = [0] * seat_count
    prev_colour = [-1] * seat_count
    prev_prev_colour = [-1] * seat_count
    opp_mask = [0] * seat_count
    repeated_opp: set[int] = set()
    seen_stamp = [0] * seat_count
    team_white = [0] * team_count
    team_black = [0] * team_count
    up = [0] * team_count
    down = [0] * team_count
    seat_down = [0] * seat_count
    seat_up = [0] * seat_count
    pair_count = [[0] * team_count for _ in range(team_count)]
    round_pairs = (len(rounds) + 1) // 2
    rp_down = [[0] * team_count for _ in range(round_pairs)]
    rp_up = [[0] * team_count for _ in range(round_pairs)]
    i5_violated = False
    spread_note: tuple[int, str, dict[str, int]] | None = None
    n_rounds = len(rounds)

    def seat_name(seat: int) -> str:
        return f'{letters[seat // players_per_team]}{seat % players_per_team + 1}'

    for r_zero, rnd in enumerate(rounds):
        r_index = r_zero + 1
        if len(rnd) != expected_boards:
            err(
                f'{label} round {r_index}: {len(rnd)} boards, '
                f'expected {expected_boards} (= {team_count} × {players_per_team}/2).'
            )
        opp_this = [[0] * team_count for _ in range(team_count)]
        floater_levels = [0] * (players_per_team + 1)
        round_pair = r_zero // 2
        for p in rnd:
            white_team = team_by_letter.get(p.white_team)
            black_team = team_by_letter.get(p.black_team)
            if white_team is None:
                err(f'{label} round {r_index}: unknown team letter {p.white_team!r}.')
            if black_team is None:
                err(f'{label} round {r_index}: unknown team letter {p.black_team!r}.')
            white_index_ok = 1 <= p.white_index <= players_per_team
            black_index_ok = 1 <= p.black_index <= players_per_team
            if not white_index_ok:
                err(
                    f'{label} round {r_index}: player index {p.white_index} out '
                    f'of range 1..{players_per_team}.'
                )
            if not black_index_ok:
                err(
                    f'{label} round {r_index}: player index {p.black_index} out '
                    f'of range 1..{players_per_team}.'
                )
            if white_team is not None and black_team is not None:
                if white_team == black_team:
                    err(f'{label} round {r_index}: team-mates paired ({p}).')

                team_white[white_team] += 1
                team_black[black_team] += 1
                opp_this[white_team][black_team] += 1
                opp_this[black_team][white_team] += 1
                pair_count[white_team][black_team] += 1
                pair_count[black_team][white_team] += 1

            white_seat = (
                white_team * players_per_team + p.white_index - 1
                if white_team is not None and white_index_ok
                else -1
            )
            black_seat = (
                black_team * players_per_team + p.black_index - 1
                if black_team is not None and black_index_ok
                else -1
            )
            for seat in (white_seat, black_seat):
                if seat < 0:
                    continue
                if seen_stamp[seat] == r_index:
                    err(
                        f'{label} round {r_index}: {seat_name(seat)} appears '
                        f'on more than one board.'
                    )
                seen_stamp[seat] = r_index
                games[seat] += 1

            if white_seat >= 0:
                white_count[white_seat] += 1
                if n_rounds >= 2:
                    prev = prev_colour[white_seat]
                    if prev == 1:
                        name = None
                        if r_zero % 2 == 1:
                            name = seat_name(white_seat)
                            err(
                                f'{label}: {name} repeats colour from round '
                                f'{r_zero} to {r_zero + 1} — only an even→odd '
                                f'boundary may repeat.'
                            )
                        if prev_prev_colour[white_seat] == prev:
                            if name is None:
                                name = seat_name(white_seat)
                            err(
                                f'{label}: {name} plays the same colour three '
                                f'rounds running (rounds {r_zero - 1}–'
                                f'{r_zero + 1}).'
                            )
                    prev_prev_colour[white_seat] = prev
                prev_colour[white_seat] = 1
                if black_team is not None:
                    mask = 1 << black_team
                    if opp_mask[white_seat] & mask:
                        repeated_opp.add(white_seat)
                    opp_mask[white_seat] |= mask
            if black_seat >= 0:
                if n_rounds >= 2:
                    prev = prev_colour[black_seat]
                    if prev == 0:
                        name = None
                        if r_zero % 2 == 1:
                            name = seat_name(black_seat)
                            err(
                                f'{label}: {name} repeats colour from round '
                                f'{r_zero} to {r_zero + 1} — only an even→odd '
                                f'boundary may repeat.'
                            )
                        if prev_prev_colour[black_seat] == prev:
                            if name is None:
                                name = seat_name(black_seat)
                            err(
                                f'{label}: {name} plays the same colour three '
                                f'rounds running (rounds {r_zero - 1}–'
                                f'{r_zero + 1}).'
                            )
                    prev_prev_colour[black_seat] = prev
                prev_colour[black_seat] = 0
                if white_team is not None:
                    mask = 1 << white_team
                    if opp_mask[black_seat] & mask:
                        repeated_opp.add(black_seat)
                    opp_mask[black_seat] |= mask

            if p.white_index < p.black_index:
                if white_team is not None:
                    down[white_team] += 1
                    if white_seat >= 0:
                        seat_down[white_seat] += 1
                    rp_down[round_pair][white_team] += 1
                    if rp_down[round_pair][white_team] > 1:
                        i5_violated = True
                if black_team is not None:
                    up[black_team] += 1
                    if black_seat >= 0:
                        seat_up[black_seat] += 1
                    rp_up[round_pair][black_team] += 1
                    if rp_up[round_pair][black_team] > 1:
                        i5_violated = True
            elif p.white_index > p.black_index:
                if white_team is not None:
                    up[white_team] += 1
                    if white_seat >= 0:
                        seat_up[white_seat] += 1
                    rp_up[round_pair][white_team] += 1
                    if rp_up[round_pair][white_team] > 1:
                        i5_violated = True
                if black_team is not None:
                    down[black_team] += 1
                    if black_seat >= 0:
                        seat_down[black_seat] += 1
                    rp_down[round_pair][black_team] += 1
                    if rp_down[round_pair][black_team] > 1:
                        i5_violated = True

            # S6a/S6b — floater rules (hard).
            if p.white_index != p.black_index:
                lo = min(p.white_index, p.black_index)
                hi = max(p.white_index, p.black_index)
                if team_count % 2 == 0:
                    err(
                        f'{label} round {r_index}: floater {p} on an even team '
                        f'count — none allowed (S6a).'
                    )
                elif not (white_index_ok and black_index_ok):
                    pass
                elif hi - lo != 1 or lo % 2 == 0:
                    err(
                        f'{label} round {r_index}: illegal floater {p} — a '
                        f'descending floater may only join consecutive boards '
                        f'with the odd board descending (S6b).'
                    )
                else:
                    floater_levels[lo] += 1

        for level, count in enumerate(floater_levels):
            if count > 1:
                err(
                    f'{label} round {r_index}: {count} descending floaters at '
                    f'board {level} — at most one is allowed per round (S6b).'
                )

        for team, counts in enumerate(opp_this):
            spread_values = [count for count in counts if count]
            if team_count > 2 and len(spread_values) == 1 and spread_values[0] > 1:
                err(
                    f'{label} round {r_index}: team {letters[team]} faces only '
                    f'one other team.'
                )
            elif (
                spread_values
                and max(spread_values) - min(spread_values) > 1
                and spread_note is None
            ):
                spread_note = (
                    r_index,
                    letters[team],
                    {letters[opp]: count for opp, count in enumerate(counts) if count},
                )

    if games and max(games) != min(games):
        err(f'{label}: players do not all play the same number of games.')
    for seat in sorted(repeated_opp):
        err(
            f'{label}: {seat_name(seat)} meets the same team twice — rounds '
            f'must be < team count.'
        )

    # Per-player colour rules (read off the official tables). Checked over a
    # multi-round set only — a single round (the autonomous one) has nothing
    # to alternate.
    if n_rounds >= 2:
        for seat, whites in enumerate(white_count):
            if abs(whites - (n_rounds - whites)) > n_rounds % 2:
                err(
                    f'{label}: {seat_name(seat)} colour imbalance '
                    f'({whites} white / {n_rounds - whites} black).'
                )
        # S6c — over the regular rounds no player is a descending floater
        # more than once (nor an ascending floater more than once).
        for seat, count in enumerate(seat_down):
            if count > 1:
                err(
                    f'{label}: {seat_name(seat)} is a descending floater '
                    f'{count} times — at most once is allowed (S6c).'
                )
        for seat, count in enumerate(seat_up):
            if count > 1:
                err(
                    f'{label}: {seat_name(seat)} is an ascending floater '
                    f'{count} times — at most once is allowed (S6c).'
                )
    for team, letter in enumerate(letters):
        if team_white[team] != team_black[team]:
            err(
                f'{label}: team {letter} colour imbalance '
                f'(white {team_white[team]} / black {team_black[team]}).'
            )

    for team, counts in enumerate(pair_count):
        non_zero_counts = [count for count in counts if count]
        if len(set(non_zero_counts)) > 1:
            note(
                f'{label}: team {letters[team]} faces an uneven number of members per '
                f'team — only the complete tables equalise this (I1).'
            )
            break
    # I3 (equal ascending/descending floaters per team) is a whole-schedule
    # ideal — meaningless for a single round (the autonomous one), where a team
    # floats at most one way. Only assess it over a multi-round set.
    unbalanced = [
        letter for team, letter in enumerate(letters) if up[team] != down[team]
    ]
    if unbalanced and n_rounds >= 2:
        note(
            f'{label}: floaters not balanced for team(s) '
            f'{", ".join(unbalanced)} — each team should have as many ascending as '
            f'descending floaters; only the complete tables equalise this (I3).'
        )
    down_counts = list(down)
    if down_counts and max(down_counts) - min(down_counts) > 1:
        note(
            f'{label}: descending floaters unequal across teams '
            f'(range {min(down_counts)}–{max(down_counts)}) — descending '
            f'floaters should be as equal as possible (spread at most 1) (I2).'
        )
    # I5 — a single-layer table (P ≤ N − 1) should float each team at most once
    # up and once down per round-pair. (For more than one layer this is
    # arithmetically impossible, so it is only checked for a single layer.)
    if team_count % 2 == 1 and 0 < players_per_team <= team_count - 1:
        if i5_violated:
            note(
                f'{label}: a team floats more than once within a round-pair — a '
                f'single-layer table should float each team at most once up and '
                f'once down per round-pair (I5).'
            )
    if spread_note is not None:
        r_index, team_name, spread = spread_note
        note(
            f'{label} round {r_index}: team {team_name} opponent spread {spread} '
            f'is uneven — a team should be spread evenly across opponents each '
            f'round; only the smaller tables equalise this (I4).'
        )


def verify_molter_table(table: 'FixedPairingTable') -> MolterReport:
    """Verify ``table`` against the Molter principles. The regular rounds
    are checked as one tournament; the autonomous round, when present, as
    a stand-alone single-round tournament."""
    report = MolterReport()
    if table.players_per_team % 2 != 0:
        report.errors.append(
            f'players-per-team must be even (got {table.players_per_team}).'
        )
    if table.regular_round_count >= table.team_count:
        report.errors.append(
            f'{table.regular_round_count} regular rounds with only '
            f'{table.team_count} teams — a player would meet a team twice '
            f'(principle 2 requires rounds < teams).'
        )
    _check_rounds(
        table.rounds, table.team_count, table.players_per_team, 'regular', report
    )
    if table.autonomous_round is not None:
        _check_rounds(
            (table.autonomous_round,),
            table.team_count,
            table.players_per_team,
            'autonomous',
            report,
        )
    return report
