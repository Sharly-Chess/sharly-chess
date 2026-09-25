"""Direct encounter (C.07 Art. 6), for individuals and teams alike.

The participants of a tied group are ranked on the points they scored
against one another. A participant's standing in that little tournament is
given as the lowest and highest score they can have in it, which differ
when games between members of the group are missing.
"""

from collections.abc import Callable, Hashable, Sequence

type MinMax[K] = Callable[[K, Sequence[K]], tuple[float, float]]
type Fallback[K] = Callable[[Sequence[K], int], None]


def split_by_score[K: Hashable](
    min_max_by_key: dict[K, tuple[float, float]],
) -> list[list[K]]:
    """The group split into the subgroups the scores keep apart, lowest
    first: a participant joins the subgroup below when their lowest score
    does not clear the best that subgroup can still do."""
    ordered = sorted(min_max_by_key.items(), key=lambda item: item[1])
    subgroups: list[list[K]] = []
    ceiling = 0.0
    for key, (lowest, highest) in ordered:
        if subgroups and lowest <= ceiling:
            subgroups[-1].append(key)
            ceiling = max(ceiling, highest)
        else:
            subgroups.append([key])
            ceiling = highest
    return subgroups


def rank_by_encounters[K: Hashable](
    group: Sequence[K],
    min_max: MinMax[K],
    values: dict[K, int],
    *,
    min_value: int = 0,
    fallback: Fallback[K] | None = None,
) -> None:
    """Give each participant of *group* a value from *min_value* up, the
    better placed the higher; participants the encounters leave level share
    a value.

    Art. 6.2: when every game between them was played, the standings between
    them place them all, each subgroup being ranked again among itself.
    Art. 6.3: with games missing, a participant is placed only when alone at
    the top whatever those games would have given, and Art. 6 is then
    reapplied to the rest. A group the encounters cannot split goes to
    *fallback* (the next score of a team, say), or is left level.
    """
    if len(group) == 1:
        values[group[0]] = min_value
        return
    min_max_by_key = {key: min_max(key, group) for key in group}
    subgroups = split_by_score(min_max_by_key)
    games_missing = any(
        lowest != highest for lowest, highest in min_max_by_key.values()
    )
    if len(subgroups) > 1 and games_missing:
        top = subgroups[-1]
        if len(top) == 1:
            rest = [key for key in group if key != top[0]]
            rank_by_encounters(
                rest, min_max, values, min_value=min_value, fallback=fallback
            )
            values[top[0]] = min_value + len(rest)
            return
        subgroups = [list(group)]
    if len(subgroups) > 1:
        for subgroup in subgroups:
            rank_by_encounters(
                subgroup, min_max, values, min_value=min_value, fallback=fallback
            )
            min_value += len(subgroup)
        return
    if fallback is not None:
        fallback(group, min_value)
        return
    for key in group:
        values[key] = min_value
