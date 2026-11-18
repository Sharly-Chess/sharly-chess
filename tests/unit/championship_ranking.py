from typing import cast

from data.championship.reconciliation import ReconciledPlayer
from data.championship.scoring import ChampionshipRule, rank_competitors


def rank_players(
    players: list[ReconciledPlayer], rules: list[ChampionshipRule]
) -> list[list[ReconciledPlayer]]:
    """Rank players only, typed so the groups read as players."""
    return cast(list[list[ReconciledPlayer]], rank_competitors([*players], rules))
