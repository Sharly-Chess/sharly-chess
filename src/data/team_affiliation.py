"""Team-affiliation sources.

An *affiliation source* derives a team's affiliation (its ``team-group``)
from its players — e.g. their common club. The teams tab offers a button
that fills every team's affiliation from a chosen source. Core ships
``club``; plugins contribute more (a federation league, a school) via the
``get_team_affiliation_sources`` hook.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from common.i18n import _

if TYPE_CHECKING:
    from data.team import Team


@dataclass(frozen=True)
class TeamAffiliationSource:
    """A way to derive a team's affiliation name. ``resolve`` returns the
    affiliation for a team, or ``None`` when it can't be determined (an
    empty team, or players that don't all share the value)."""

    id: str
    label: str
    resolve: Callable[['Team'], str | None]


def team_shared_player_value(
    team: 'Team', getter: Callable[[Any], str | None]
) -> str | None:
    """The value ``getter`` returns for *every* player of ``team`` when they
    all share a single non-empty one; ``None`` otherwise (empty team, a
    player missing the value, or differing values). The building block for
    "all players must share the same X" affiliation sources."""
    players = list(team.players)
    if not players:
        return None
    values: set[str] = set()
    for player in players:
        value = getter(player)
        if not value:
            return None
        values.add(value)
    return values.pop() if len(values) == 1 else None


def core_team_affiliation_sources() -> list[TeamAffiliationSource]:
    return [
        TeamAffiliationSource(
            id='club',
            label=_('Club of the players'),
            resolve=lambda team: team_shared_player_value(
                team, lambda player: player.club.name or None
            ),
        ),
    ]
