import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from logging import Logger
from pathlib import Path
from urllib.parse import quote

from common import ARCHIVES_DIR, CHAMPIONSHIP_DIR
from common.logger import get_logger
from data.championship.championship import Championship
from data.championship.options import (
    ChampionshipCompetitorType,
    TeamScoreBasis,
)
from database.sqlite.championship.championship_database import ChampionshipDatabase
from database.sqlite.championship.championship_store import (
    StoredChampionshipCategory,
    StoredChampionshipCriterion,
    StoredChampionship,
    StoredChampionshipSource,
    StoredChampionshipPlayerOverride,
    StoredChampionshipTeamOverride,
    StoredChampionshipRule,
)
from utils import Utils
from utils.enum import Extension

logger: Logger = get_logger()


@dataclass
class ChampionshipArchive:
    file: Path
    name: str
    date: datetime

    @property
    def date_str(self) -> str:
        from utils.date_time import format_datetime

        return format_datetime(self.date)

    @property
    def url_name(self) -> str:
        return quote(self.name)

    @cached_property
    def championship(self) -> Championship:
        database = ChampionshipDatabase(file_path=self.file)
        if not database.check_status():
            database.upgrade()
        with ChampionshipDatabase(file_path=self.file) as database:
            stored_championship = database.load_stored_championship()
        return Championship(stored_championship, self.name.split('#')[0])

    @property
    def display_name(self) -> str:
        return self.championship.name

    def restore(self) -> str | None:
        loader = ChampionshipLoader()
        uniq_id = loader.get_unused_championship_uniq_id(self.name.split('#')[0])
        new_path = ChampionshipDatabase.championship_database_path(uniq_id)
        shutil.copy(self.file, new_path)
        try:
            loader.load_championship(uniq_id)
        except Exception as error:
            logger.exception(error)
            new_path.unlink(missing_ok=True)
            return None
        self.file.unlink()
        return uniq_id


class ChampionshipArchiveLoader:
    @staticmethod
    def get_archive_path(archive_name: str) -> Path:
        return ARCHIVES_DIR / f'{archive_name}.{Extension.CHAMPIONSHIP_DB}'

    @classmethod
    def get_sorted_archives(cls) -> list[ChampionshipArchive]:
        return sorted(
            [
                ChampionshipArchive(
                    file,
                    file.stem,
                    datetime.fromtimestamp(file.lstat().st_ctime),
                )
                for file in ARCHIVES_DIR.glob(f'*.{Extension.CHAMPIONSHIP_DB}')
            ],
            key=lambda archive: archive.date,
        )

    @classmethod
    def get_archive(cls, archive_name: str) -> ChampionshipArchive | None:
        file = cls.get_archive_path(archive_name)
        if not file.exists():
            return None
        return ChampionshipArchive(
            file,
            file.stem,
            datetime.fromtimestamp(file.lstat().st_ctime),
        )


class ChampionshipLoader:
    """Lists, creates, loads and deletes championship (``.scch``) files, mirroring
    :class:`EventLoader`. Each championship lives in its own file, identified by
    its uniq_id (the file stem)."""

    @classmethod
    def format_uniq_id(cls, uniq_id: str) -> str:
        """Return a filename-safe unique ID, matching ``EventLoader``."""
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', uniq_id)

    @classmethod
    def all_championship_ids(cls) -> list[str]:
        ids: list[str] = []
        for file in CHAMPIONSHIP_DIR.glob(f'*.{Extension.CHAMPIONSHIP_DB}'):
            uniq_id = cls.format_uniq_id(file.stem)
            if uniq_id != file.stem:
                index = 1
                new_file = ChampionshipDatabase.championship_database_path(uniq_id)
                while new_file.exists():
                    index += 1
                    new_file = ChampionshipDatabase.championship_database_path(
                        f'{uniq_id}-{index}'
                    )
                shutil.move(file, new_file)
                logger.warning(
                    'File [%s] has been renamed [%s]', file.name, new_file.name
                )
                uniq_id = new_file.stem
            ids.append(uniq_id)
        return ids

    def get_unused_championship_uniq_id(self, base_uniq_id: str) -> str:
        return Utils.get_unused_item_uniq_id(
            Utils.name_to_uniq_id(base_uniq_id), self.all_championship_ids()
        )

    def create_championship(
        self,
        name: str,
        competitor_type: str = ChampionshipCompetitorType.INDIVIDUAL,
    ) -> str:
        """Create a new championship from a display name and return its uniq_id."""
        competitor_type = ChampionshipCompetitorType(competitor_type).value
        uniq_id = self.get_unused_championship_uniq_id(name)
        ChampionshipDatabase(uniq_id).create()
        with ChampionshipDatabase(uniq_id, write=True) as database:
            database.update_stored_championship(
                StoredChampionship(name=name, competitor_type=competitor_type)
            )
        return uniq_id

    def load_championship(self, uniq_id: str) -> Championship:
        database = ChampionshipDatabase(uniq_id)
        if not database.check_status():
            database.upgrade()
        with ChampionshipDatabase(uniq_id) as database:
            stored_championship = database.load_stored_championship()
        return Championship(stored_championship, uniq_id)

    def delete_championship(self, uniq_id: str):
        ChampionshipDatabase(uniq_id).file.unlink(missing_ok=True)

    def rename_championship(self, uniq_id: str, new_uniq_id: str):
        ChampionshipDatabase(uniq_id).rename(new_uniq_id)

    def set_name(self, championship_uniq_id: str, name: str):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            stored_championship = database.load_stored_championship()
            stored_championship.name = name
            database.update_stored_championship(stored_championship)

    def archive_championship(self, uniq_id: str) -> Path:
        source = ChampionshipDatabase.championship_database_path(uniq_id)
        index = 0
        archive = ChampionshipArchiveLoader.get_archive_path(uniq_id)
        while archive.exists():
            index += 1
            archive = ChampionshipArchiveLoader.get_archive_path(f'{uniq_id}#{index}')
        source.rename(archive)
        return archive

    # -------------------------------------------------------------------------
    # Sources
    # -------------------------------------------------------------------------

    def add_source(
        self, championship_uniq_id: str, event_uniq_id: str, tournament_id: int
    ) -> StoredChampionshipSource:
        """Reference a tournament, snapshotting its event/tournament name and
        date so the source stays labelled if it is later deleted."""
        from data.loader import EventLoader

        event_name: str | None = None
        tournament_name: str | None = None
        start_date = None
        stop_date = None
        try:
            event = EventLoader().load_event(event_uniq_id)
            with ChampionshipDatabase(championship_uniq_id) as database:
                stored_championship = database.load_stored_championship()
            expected_type = ChampionshipCompetitorType(
                stored_championship.competitor_type
            )
            source_type = (
                ChampionshipCompetitorType.TEAM
                if event.is_team_event
                else ChampionshipCompetitorType.INDIVIDUAL
            )
            if source_type != expected_type:
                raise ValueError(
                    f'Cannot add a {source_type.value.lower()} tournament to a '
                    f'{expected_type.value.lower()} championship'
                )
            event_name = event.name
            tournament = event.tournaments_by_id.get(tournament_id)
            if tournament is not None:
                tournament_name = tournament.name
                start_date = tournament.start_date
                stop_date = tournament.stop_date
        except ValueError:
            raise
        except Exception as error:
            logger.warning(
                'Championship [%s]: snapshotting source [%s/%s] failed: %s',
                championship_uniq_id,
                event_uniq_id,
                tournament_id,
                error,
            )

        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            existing = database.load_stored_sources()
            next_index = 1 + max((source.index for source in existing), default=0)
            return database.add_stored_source(
                StoredChampionshipSource(
                    id=None,
                    event_uniq_id=event_uniq_id,
                    tournament_id=tournament_id,
                    index=next_index,
                    event_name=event_name,
                    tournament_name=tournament_name,
                    start_date=start_date,
                    stop_date=stop_date,
                )
            )

    def delete_source(self, championship_uniq_id: str, source_id: int):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_source(source_id)

    # -------------------------------------------------------------------------
    # Player identity overrides
    # -------------------------------------------------------------------------

    def merge_players(
        self,
        championship_uniq_id: str,
        refs: list[tuple[str, int, int]],
        group_key: str,
    ):
        """Force the given source players — ``(event_uniq_id, tournament_id,
        source_player_id)`` tuples — into the same reconciled player by pinning
        them all to ``group_key``."""
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            for event_uniq_id, tournament_id, source_player_id in refs:
                database.set_stored_player_override(
                    StoredChampionshipPlayerOverride(
                        id=None,
                        event_uniq_id=event_uniq_id,
                        tournament_id=tournament_id,
                        source_player_id=source_player_id,
                        group_key=group_key,
                    )
                )

    def clear_player_override(
        self,
        championship_uniq_id: str,
        event_uniq_id: str,
        tournament_id: int,
        source_player_id: int,
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_player_override(
                event_uniq_id, tournament_id, source_player_id
            )

    def clear_player_override_group(self, championship_uniq_id: str, group_key: str):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_player_override_group(group_key)

    def merge_teams(
        self,
        championship_uniq_id: str,
        refs: list[tuple[str, int, int]],
        group_key: str,
    ):
        """Force source-team references into the same reconciled team."""
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            for event_uniq_id, tournament_id, source_team_id in refs:
                database.set_stored_team_override(
                    StoredChampionshipTeamOverride(
                        id=None,
                        event_uniq_id=event_uniq_id,
                        tournament_id=tournament_id,
                        source_team_id=source_team_id,
                        group_key=group_key,
                    )
                )

    def clear_team_override(
        self,
        championship_uniq_id: str,
        event_uniq_id: str,
        tournament_id: int,
        source_team_id: int,
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_team_override(
                event_uniq_id, tournament_id, source_team_id
            )

    def clear_team_override_group(self, championship_uniq_id: str, group_key: str):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_team_override_group(group_key)

    # -------------------------------------------------------------------------
    # Championship rules
    # -------------------------------------------------------------------------

    def set_championship_rules(self, championship_uniq_id: str, rules: list[tuple]):
        """Replace the ordered rule list, in application order. Each rule is a
        ``(type, best_n)`` pair, optionally with a third ``options`` dict (e.g.
        an F1 points table, or the place a "number of placings" rule counts)."""
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.replace_stored_championship_rules(
                [
                    StoredChampionshipRule(
                        id=None,
                        index=index,
                        type=rule[0],
                        best_n=rule[1],
                        options=rule[2] if len(rule) > 2 else {},
                    )
                    for index, rule in enumerate(rules)
                ]
            )

    def add_championship_rule(
        self, championship_uniq_id: str, stored_rule: StoredChampionshipRule
    ) -> StoredChampionshipRule:
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            stored_rule.index = len(database.load_stored_championship_rules())
            return database.add_stored_championship_rule(stored_rule)

    def update_championship_rule(
        self, championship_uniq_id: str, stored_rule: StoredChampionshipRule
    ) -> StoredChampionshipRule:
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            return database.update_stored_championship_rule(stored_rule)

    def delete_championship_rule(self, championship_uniq_id: str, rule_id: int):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_championship_rule(rule_id)

    def reorder_championship_rules(
        self, championship_uniq_id: str, rule_ids: list[int]
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.reorder_stored_championship_rules(rule_ids)

    def set_manual_tiebreaks(
        self, championship_uniq_id: str, updates: dict[str, int | None]
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.set_stored_manual_tiebreaks(updates)

    def reset_manual_tiebreaks(self, championship_uniq_id: str):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_manual_tiebreaks()

    def set_source_coefficient(
        self, championship_uniq_id: str, source_id: int, coefficient: float
    ):
        """Set the weight applied to a stage's points and tie-break values."""
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            sources = {source.id: source for source in database.load_stored_sources()}
            stored_source = sources.get(source_id)
            if stored_source is None:
                return
            stored_source.coefficient = coefficient
            database.update_stored_source(stored_source)

    # -------------------------------------------------------------------------
    # Championship categories
    # -------------------------------------------------------------------------

    def set_age_category_base_date(
        self, championship_uniq_id: str, base_date: date | None
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            stored_championship = database.load_stored_championship()
            stored_championship.age_category_base_date = base_date
            database.update_stored_championship(stored_championship)

    def set_team_score_basis(self, championship_uniq_id: str, score_basis: str):
        score_basis = TeamScoreBasis(score_basis).value
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            stored_championship = database.load_stored_championship()
            if (
                ChampionshipCompetitorType(stored_championship.competitor_type)
                != ChampionshipCompetitorType.TEAM
            ):
                raise ValueError('Team score basis only applies to a team championship')
            stored_championship.team_score_basis = score_basis
            database.update_stored_championship(stored_championship)

    def set_championship_categories(
        self,
        championship_uniq_id: str,
        categories: list[StoredChampionshipCategory],
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            if (
                ChampionshipCompetitorType(
                    database.load_stored_championship().competitor_type
                )
                == ChampionshipCompetitorType.TEAM
                and categories
            ):
                raise ValueError(
                    'Player-filter categories do not apply to a team championship'
                )
            database.replace_stored_championship_categories(categories)

    def add_championship_category(
        self,
        championship_uniq_id: str,
        category: StoredChampionshipCategory,
    ) -> StoredChampionshipCategory:
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            stored_championship = database.load_stored_championship()
            if (
                ChampionshipCompetitorType(stored_championship.competitor_type)
                == ChampionshipCompetitorType.TEAM
            ):
                raise ValueError(
                    'Player-filter categories do not apply to a team championship'
                )
            return database.add_stored_championship_category(category)

    def rename_championship_category(
        self, championship_uniq_id: str, category_id: int, name: str
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.rename_stored_championship_category(category_id, name)

    def delete_championship_category(self, championship_uniq_id: str, category_id: int):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_championship_category(category_id)

    def reorder_championship_categories(
        self, championship_uniq_id: str, category_ids: list[int]
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.reorder_stored_championship_categories(category_ids)

    def add_championship_criterion(
        self,
        championship_uniq_id: str,
        criterion: StoredChampionshipCriterion,
    ) -> StoredChampionshipCriterion:
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            return database.add_stored_championship_criterion(criterion)

    def update_championship_criterion(
        self,
        championship_uniq_id: str,
        criterion: StoredChampionshipCriterion,
    ) -> StoredChampionshipCriterion:
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            return database.update_stored_championship_criterion(criterion)

    def delete_championship_criterion(
        self, championship_uniq_id: str, category_id: int, criterion_id: int
    ):
        with ChampionshipDatabase(championship_uniq_id, write=True) as database:
            database.delete_stored_championship_criterion(category_id, criterion_id)

    # -------------------------------------------------------------------------
    # Reverse lookup (delete-time guard)
    # -------------------------------------------------------------------------

    @classmethod
    def rename_event_references(cls, old_event_uniq_id: str, new_event_uniq_id: str):
        """Repoint every championship that references a renamed event, so its
        sources and identity overrides keep resolving."""
        if old_event_uniq_id == new_event_uniq_id:
            return
        for championship_uniq_id in cls.championship_ids_referencing(old_event_uniq_id):
            try:
                with ChampionshipDatabase(championship_uniq_id, write=True) as database:
                    database.rename_event_references(
                        old_event_uniq_id, new_event_uniq_id
                    )
            except Exception as error:
                logger.warning(
                    'Championship [%s]: could not repoint renamed event [%s]: %s',
                    championship_uniq_id,
                    old_event_uniq_id,
                    error,
                )

    @classmethod
    def championship_ids_referencing(
        cls, event_uniq_id: str, tournament_id: int | None = None
    ) -> list[str]:
        """uniq_ids of every championship referencing the given event (optionally
        a specific tournament). Used to warn before deleting an event or a
        tournament that a championship depends on."""
        referencing: list[str] = []
        for championship_uniq_id in cls.all_championship_ids():
            try:
                with ChampionshipDatabase(championship_uniq_id) as database:
                    sources = database.load_stored_sources()
            except Exception as error:
                logger.warning(
                    'Championship [%s]: reverse-lookup failed: %s',
                    championship_uniq_id,
                    error,
                )
                continue
            for source in sources:
                if source.event_uniq_id != event_uniq_id:
                    continue
                if tournament_id is None or source.tournament_id == tournament_id:
                    referencing.append(championship_uniq_id)
                    break
        return referencing
