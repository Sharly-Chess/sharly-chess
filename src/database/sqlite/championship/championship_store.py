from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class StoredChampionshipSource:
    """A tournament referenced by a championship, belonging to an independent
    event. ``event_uniq_id`` + ``tournament_id`` locate it; the snapshot fields
    keep a readable label when the source can no longer be resolved."""

    id: int | None
    event_uniq_id: str = ''
    tournament_id: int = 0
    index: int = 0
    event_name: str | None = None
    tournament_name: str | None = None
    start_date: date | None = None
    stop_date: date | None = None
    coefficient: float = 1.0


@dataclass
class StoredChampionshipPlayerOverride:
    """A manual identity decision pinning a source player to a named group.

    Players are reconciled across sources live; an override adds ``group_key``
    as an extra identity key so participants sharing it are forced into the same
    reconciled player, regardless of what the automatic match found."""

    id: int | None
    event_uniq_id: str = ''
    tournament_id: int = 0
    source_player_id: int = 0
    group_key: str = ''


@dataclass
class StoredChampionshipTeamOverride:
    """A manual identity decision pinning a source team to a named group."""

    id: int | None
    event_uniq_id: str = ''
    tournament_id: int = 0
    source_team_id: int = 0
    group_key: str = ''


@dataclass
class StoredChampionshipRule:
    """One ordered championship scoring criterion. ``type`` is a rule's
    ``static_id()``; ``best_n`` scopes it to a competitor's best N stages by
    points (``None`` = all stages); ``options`` carries rule-specific config
    (e.g. an F1 points table, or the place a "number of placings" rule counts)."""

    id: int | None
    index: int = 0
    type: str = ''
    best_n: int | None = None
    options: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class StoredChampionshipCriterion:
    """One player filter belonging to a championship category.

    ``type`` and ``options`` use the same identifiers and option payloads as
    prize-category player filters, so the Championship UI can reuse that
    vocabulary (AGE, GENDER, and plugin-provided custom filters).
    """

    id: int | None
    championship_category_id: int | None = None
    type: str = ''
    options: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class StoredChampionshipCategory:
    """A named filtered view of the Championship standings."""

    id: int | None
    name: str = ''
    index: int = 0
    stored_criteria: list[StoredChampionshipCriterion] = field(
        default_factory=list[StoredChampionshipCriterion]
    )


@dataclass
class StoredChampionship:
    """The single championship held in a ``.scch`` file.

    A championship aggregates results from tournaments belonging to independent
    events. Its ``uniq_id`` is the file stem, so it is not stored in the
    database (mirrors :class:`StoredEvent`)."""

    name: str = ''
    competitor_type: str = 'INDIVIDUAL'
    team_score_basis: str = 'SOURCE_PRIMARY'
    age_category_base_date: date | None = None
    stored_sources: list[StoredChampionshipSource] = field(
        default_factory=list[StoredChampionshipSource]
    )
    stored_player_overrides: list[StoredChampionshipPlayerOverride] = field(
        default_factory=list[StoredChampionshipPlayerOverride]
    )
    stored_team_overrides: list[StoredChampionshipTeamOverride] = field(
        default_factory=list[StoredChampionshipTeamOverride]
    )
    stored_championship_rules: list[StoredChampionshipRule] = field(
        default_factory=list[StoredChampionshipRule]
    )
    stored_championship_categories: list[StoredChampionshipCategory] = field(
        default_factory=list[StoredChampionshipCategory]
    )
    # Reconciled-competitor key -> pinned manual tie-break position.
    stored_manual_tiebreaks: dict[str, int] = field(default_factory=dict[str, int])
