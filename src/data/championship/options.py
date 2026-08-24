"""Persisted Championship mode options."""

from enum import StrEnum


class ChampionshipCompetitorType(StrEnum):
    INDIVIDUAL = 'INDIVIDUAL'
    TEAM = 'TEAM'


class TeamScoreBasis(StrEnum):
    SOURCE_PRIMARY = 'SOURCE_PRIMARY'
    MATCH_POINTS = 'MATCH_POINTS'
    GAME_POINTS = 'GAME_POINTS'
