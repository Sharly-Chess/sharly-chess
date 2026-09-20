"""The recipe replay, pinned.

The recipes are packed schedules; replaying one is arithmetic — the
shifts, factors and colour bits that expand it — and a slip in it can
still produce a table the verifier accepts. These tables are what the
recipes expand to today, for a few shapes on either side of the
one-odd repair: change the expansion, and they say so.
"""

import pytest

from data.pairings.molter_recipes import get_molter_recipe_table

REPLAYS: dict[tuple[int, int, int], list[str]] = {
    (5, 2, 4): [
        'C1-D1 E1-A1 D2-B1 A2-C2 B2-E2',
        'B1-A1 D1-E1 E2-C1 A2-D2 C2-B2',
        'A1-C1 B1-E1 D1-B2 C2-D2 E2-A2',
        'A1-D1 C1-B1 E1-C2 B2-A2 D2-E2',
    ],
    (7, 2, 6): [
        'B1-A1 C1-G1 E1-F1 D1-G2 B2-C2 E2-D2 F2-A2',
        'A1-D1 F1-C1 G1-B1 C2-E1 A2-E2 D2-B2 G2-F2',
        'C1-D1 E1-B1 G1-A1 F1-B2 A2-C2 F2-D2 G2-E2',
        'A1-F1 B1-C1 D1-E1 D2-G1 B2-A2 C2-G2 E2-F2',
        'B1-D1 E1-A1 F1-G1 C1-E2 A2-D2 B2-G2 C2-F2',
        'A1-C1 D1-F1 G1-E1 F2-B1 D2-C2 E2-B2 G2-A2',
    ],
    (5, 4, 4): [
        'B1-E1 D1-C1 C2-A1 A2-B2 E2-D2 A3-D3 B3-C3 E3-A4 C4-E4 D4-B4',
        'B1-C1 E1-A1 D1-B2 A2-D2 C2-E2 B3-A3 D3-E3 C3-D4 A4-C4 E4-B4',
        'A1-B1 E1-D1 C1-A2 B2-E2 D2-C2 C3-E3 D3-B3 E4-A3 A4-D4 B4-C4',
        'A1-D1 C1-E1 D2-B1 B2-C2 E2-A2 A3-C3 E3-B3 C4-D3 B4-A4 D4-E4',
    ],
    (8, 4, 7): [
        'A1-H1 B1-G1 C1-F1 D1-E1 B2-H2 C2-A2 E2-F2 G2-D2 A3-E3 D3-B3 F3-G3 H3-C3 E4-C4 F4-B4 G4-A4 H4-D4',
        'A1-B1 F1-D1 G1-C1 H1-E1 B2-C2 D2-A2 E2-G2 F2-H2 A3-F3 C3-D3 E3-B3 G3-H3 B4-G4 C4-F4 D4-E4 H4-A4',
        'B1-H1 C1-A1 D1-G1 E1-F1 A2-E2 D2-B2 F2-G2 H2-C2 B3-F3 C3-E3 G3-A3 H3-D3 A4-B4 E4-H4 F4-D4 G4-C4',
        'A1-D1 B1-C1 F1-H1 G1-E1 A2-F2 C2-D2 E2-B2 G2-H2 B3-G3 D3-E3 F3-C3 H3-A3 C4-A4 D4-G4 E4-F4 H4-B4',
        'D1-B1 E1-A1 F1-G1 H1-C1 B2-F2 C2-E2 G2-A2 H2-D2 A3-B3 C3-G3 D3-F3 E3-H3 A4-D4 B4-C4 F4-H4 G4-E4',
        'A1-F1 B1-E1 C1-D1 G1-H1 B2-G2 D2-E2 F2-C2 H2-A2 A3-C3 E3-F3 G3-D3 H3-B3 C4-H4 D4-B4 E4-A4 F4-G4',
        'E1-C1 F1-B1 G1-A1 H1-D1 A2-B2 C2-G2 D2-F2 E2-H2 B3-C3 D3-A3 F3-H3 G3-E3 A4-F4 B4-E4 C4-D4 H4-G4',
    ],
    (9, 4, 8): [
        'C1-D1 F1-A1 G1-I1 H1-E1 B1-F2 C2-B2 D2-E2 H2-G2 I2-A2 D3-H3 E3-G3 F3-C3 I3-B3 C4-A3 A4-H4 D4-I4 E4-F4 G4-B4',
        'A1-G1 D1-F1 E1-B1 I1-H1 G2-C1 A2-D2 B2-H2 E2-C2 F2-I2 A3-E3 B3-D3 C3-I3 H3-F3 G3-D4 B4-A4 F4-G4 H4-C4 I4-E4',
        'A1-H1 E1-G1 F1-C1 I1-B1 D1-H2 C2-A2 D2-I2 E2-F2 G2-B2 A3-F3 C3-B3 D3-E3 I3-G3 H3-E4 A4-I4 B4-F4 C4-D4 H4-G4',
        'B1-A1 C1-I1 G1-D1 H1-F1 I2-E1 A2-E2 B2-D2 F2-G2 H2-C2 B3-H3 E3-C3 F3-D3 G3-A3 F4-I3 D4-A4 E4-B4 G4-C4 I4-H4',
        'C1-B1 D1-E1 H1-G1 I1-A1 B2-F1 C2-D2 F2-A2 G2-I2 H2-E2 A3-H3 D3-I3 E3-F3 G3-B3 C3-A4 D4-H4 E4-G4 F4-C4 I4-B4',
        'A1-D1 B1-H1 E1-C1 F1-I1 G1-C2 A2-G2 D2-F2 E2-B2 I2-H2 B3-A3 F3-G3 H3-C3 I3-E3 G4-D3 A4-E4 B4-D4 C4-I4 H4-F4',
        'C1-A1 D1-I1 E1-F1 G1-B1 D2-H1 A2-H2 E2-G2 F2-C2 I2-B2 A3-I3 B3-F3 C3-D3 H3-G3 H4-E3 A4-F4 C4-B4 D4-E4 I4-G4',
        'A1-E1 B1-D1 F1-G1 H1-C1 I1-E2 B2-A2 C2-I2 G2-D2 H2-F2 D3-A3 E3-B3 G3-C3 I3-H3 F3-I4 B4-H4 E4-C4 F4-D4 G4-A4',
    ],
    (11, 2, 10): [
        'B1-C1 G1-F1 H1-I1 J1-D1 K1-A1 J2-E1 A2-I2 D2-C2 F2-E2 G2-H2 K2-B2',
        'A1-J1 C1-G1 D1-H1 E1-K1 I1-B1 F1-K2 B2-D2 C2-F2 E2-A2 H2-J2 I2-G2',
        'B1-J1 C1-K1 E1-H1 F1-A1 I1-D1 D2-G1 B2-E2 C2-J2 G2-A2 H2-K2 I2-F2',
        'A1-C1 D1-E1 G1-B1 J1-F1 K1-I1 H1-B2 A2-D2 E2-C2 F2-H2 J2-I2 K2-G2',
        'B1-A1 D1-F1 E1-G1 H1-C1 J1-K1 I1-C2 A2-H2 B2-F2 D2-K2 G2-J2 I2-E2',
        'A1-I1 C1-D1 F1-E1 G1-H1 K1-B1 E2-J1 C2-B2 F2-G2 H2-I2 J2-D2 K2-A2',
        'D1-B1 E1-A1 F1-C1 G1-I1 J1-H1 K1-F2 A2-J2 B2-I2 C2-G2 D2-H2 E2-K2',
        'A1-G1 B1-E1 C1-J1 H1-K1 I1-F1 G2-D1 F2-A2 H2-E2 I2-D2 J2-B2 K2-C2',
        'C1-E1 D1-A1 G1-K1 H1-F1 I1-J1 B1-H2 B2-G2 C2-A2 E2-D2 F2-J2 K2-I2',
        'A1-H1 E1-I1 F1-B1 J1-G1 K1-D1 I2-C1 A2-B2 D2-F2 G2-E2 H2-C2 J2-K2',
    ],
}


@pytest.mark.unit
@pytest.mark.parametrize(('shape', 'rounds'), REPLAYS.items(), ids=str)
def test_the_recipe_replays_to_the_same_table(
    shape: tuple[int, int, int], rounds: list[str]
) -> None:
    table = get_molter_recipe_table(*shape)
    assert table is not None
    assert [
        ' '.join(
            f'{p.white_team}{p.white_index}-{p.black_team}{p.black_index}'
            for p in round_
        )
        for round_ in table.rounds
    ] == rounds
