from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Any, TYPE_CHECKING

from packaging.version import Version

from common import CHAMPIONSHIP_DIR
from common.logger import get_logger
from database.sqlite.championship import migrations
from database.sqlite.championship.championship_store import (
    StoredChampionshipCategory,
    StoredChampionshipCriterion,
    StoredChampionship,
    StoredChampionshipSource,
    StoredChampionshipPlayerOverride,
    StoredChampionshipTeamOverride,
    StoredChampionshipRule,
)
from database.sqlite.migration_database import MigrationDatabase
from utils.enum import Extension

if TYPE_CHECKING:
    from database.sqlite.migration import DatabaseMigrationManager

logger: Logger = get_logger()


class ChampionshipDatabase(MigrationDatabase):
    """The SQLite database class for a Sharly Chess championship (``.scch``).

    One file per championship, mirroring :class:`EventDatabase`: it can be opened
    with a ``uniq_id`` (the file stem) or an explicit ``file_path``, and carries
    its own migration timeline."""

    def __init__(
        self,
        uniq_id: str | None = None,
        write: bool = False,
        *,
        file_path: Path | None = None,
        enable_foreign_keys: bool = True,
    ):
        if uniq_id is not None and file_path is not None:
            raise ValueError('Cannot specify both uniq_id and file_path')
        if uniq_id is None and file_path is None:
            raise ValueError('Must specify either uniq_id or file_path')

        if file_path is not None:
            self.uniq_id = file_path.stem
        else:
            assert uniq_id is not None
            self.uniq_id = uniq_id
            file_path = self.championship_database_path(self.uniq_id)
        super().__init__(file_path, write, enable_foreign_keys=enable_foreign_keys)

    @cached_property
    def migration_managers(self) -> list['DatabaseMigrationManager']:
        from database.sqlite.migration import DatabaseMigrationManager

        return [DatabaseMigrationManager(self, migrations)]

    @property
    def migration_by_legacy_version(self) -> dict[Version, str]:
        # Brand-new database type: no legacy (pre-metadata) versions to map.
        return {}

    @property
    def migration_instance_kwargs(self) -> dict[str, Any]:
        return {'file_path': self.file}

    @property
    def log_prefix(self) -> str:
        return f'Championship database [{self.uniq_id}] - '

    @staticmethod
    def championship_database_path(uniq_id: str) -> Path:
        return CHAMPIONSHIP_DIR / f'{uniq_id}.{Extension.CHAMPIONSHIP_DB}'

    def rename(self, new_uniq_id: str):
        """Move the championship file to the one for ``new_uniq_id``."""
        self.file.rename(self.championship_database_path(new_uniq_id))

    # ---------------------------------------------------------------------------------
    # Championship
    # ---------------------------------------------------------------------------------

    def _row_to_stored_championship(self, row: dict[str, Any]) -> StoredChampionship:
        return StoredChampionship(
            name=row['name'],
            competitor_type=row['competitor_type'],
            team_score_basis=row['team_score_basis'],
            age_category_base_date=self.load_optional_date_from_database_field(
                row['age_category_base_date']
            ),
            min_participation=row['min_participation'],
        )

    def load_stored_championship(self) -> StoredChampionship:
        self.execute('SELECT * FROM `info`')
        stored_championship = self._row_to_stored_championship(self.fetchone())
        stored_championship.stored_sources = self.load_stored_sources()
        stored_championship.stored_player_overrides = (
            self.load_stored_player_overrides()
        )
        stored_championship.stored_team_overrides = self.load_stored_team_overrides()
        stored_championship.stored_championship_rules = (
            self.load_stored_championship_rules()
        )
        stored_championship.stored_championship_categories = (
            self.load_stored_championship_categories()
        )
        stored_championship.stored_manual_tiebreaks = (
            self.load_stored_manual_tiebreaks()
        )
        return stored_championship

    def update_stored_championship(
        self, stored_championship: StoredChampionship
    ) -> StoredChampionship:
        self.execute(
            'UPDATE `info` SET `name` = ?, `competitor_type` = ?, '
            '`team_score_basis` = ?, `age_category_base_date` = ?, '
            '`min_participation` = ?',
            (
                stored_championship.name,
                stored_championship.competitor_type,
                stored_championship.team_score_basis,
                self.dump_date_to_database_field(
                    stored_championship.age_category_base_date
                ),
                stored_championship.min_participation,
            ),
        )
        return self.load_stored_championship()

    # ---------------------------------------------------------------------------------
    # Sources
    # ---------------------------------------------------------------------------------

    def _row_to_stored_source(self, row: dict[str, Any]) -> StoredChampionshipSource:
        return StoredChampionshipSource(
            id=row['id'],
            event_uniq_id=row['event_uniq_id'],
            tournament_id=row['tournament_id'],
            index=row['index'],
            event_name=row['event_name'],
            tournament_name=row['tournament_name'],
            start_date=self.load_optional_date_from_database_field(row['start_date']),
            stop_date=self.load_optional_date_from_database_field(row['stop_date']),
            coefficient=row['coefficient'],
        )

    def load_stored_sources(self) -> list[StoredChampionshipSource]:
        self.execute('SELECT * FROM `source` ORDER BY `index`, `id`')
        return [self._row_to_stored_source(row) for row in self.fetchall()]

    def add_stored_source(
        self, stored_source: StoredChampionshipSource
    ) -> StoredChampionshipSource:
        self.execute(
            'INSERT INTO `source` ('
            '   `index`, `event_uniq_id`, `tournament_id`,'
            '   `event_name`, `tournament_name`, `start_date`, `stop_date`,'
            '   `coefficient`'
            ') VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                stored_source.index,
                stored_source.event_uniq_id,
                stored_source.tournament_id,
                stored_source.event_name,
                stored_source.tournament_name,
                self.dump_date_to_database_field(stored_source.start_date),
                self.dump_date_to_database_field(stored_source.stop_date),
                stored_source.coefficient,
            ),
        )
        stored_source.id = self._last_inserted_id()
        return stored_source

    def update_stored_source(
        self, stored_source: StoredChampionshipSource
    ) -> StoredChampionshipSource:
        self.execute(
            'UPDATE `source` SET '
            '   `index` = ?, `event_uniq_id` = ?, `tournament_id` = ?,'
            '   `event_name` = ?, `tournament_name` = ?, `start_date` = ?, '
            '   `stop_date` = ?, `coefficient` = ? '
            'WHERE `id` = ?',
            (
                stored_source.index,
                stored_source.event_uniq_id,
                stored_source.tournament_id,
                stored_source.event_name,
                stored_source.tournament_name,
                self.dump_date_to_database_field(stored_source.start_date),
                self.dump_date_to_database_field(stored_source.stop_date),
                stored_source.coefficient,
                stored_source.id,
            ),
        )
        return stored_source

    def delete_stored_source(self, source_id: int):
        self.execute('DELETE FROM `source` WHERE `id` = ?', (source_id,))

    # ---------------------------------------------------------------------------------
    # Player overrides
    # ---------------------------------------------------------------------------------

    def _row_to_stored_player_override(
        self, row: dict[str, Any]
    ) -> StoredChampionshipPlayerOverride:
        return StoredChampionshipPlayerOverride(
            id=row['id'],
            event_uniq_id=row['event_uniq_id'],
            tournament_id=row['tournament_id'],
            source_player_id=row['source_player_id'],
            group_key=row['group_key'],
        )

    def load_stored_player_overrides(self) -> list[StoredChampionshipPlayerOverride]:
        self.execute('SELECT * FROM `player_override` ORDER BY `id`')
        return [self._row_to_stored_player_override(row) for row in self.fetchall()]

    def set_stored_player_override(
        self, stored_override: StoredChampionshipPlayerOverride
    ) -> StoredChampionshipPlayerOverride:
        """Insert or replace the override for a source player (there is at most
        one per ``(event, tournament, source player)``)."""
        self.execute(
            'INSERT INTO `player_override` ('
            '   `event_uniq_id`, `tournament_id`, `source_player_id`, `group_key`'
            ') VALUES (?, ?, ?, ?) '
            'ON CONFLICT(`event_uniq_id`, `tournament_id`, `source_player_id`) '
            'DO UPDATE SET `group_key` = excluded.`group_key`',
            (
                stored_override.event_uniq_id,
                stored_override.tournament_id,
                stored_override.source_player_id,
                stored_override.group_key,
            ),
        )
        return stored_override

    def delete_stored_player_override(
        self, event_uniq_id: str, tournament_id: int, source_player_id: int
    ):
        self.execute(
            'DELETE FROM `player_override` '
            'WHERE `event_uniq_id` = ? AND `tournament_id` = ? '
            'AND `source_player_id` = ?',
            (event_uniq_id, tournament_id, source_player_id),
        )

    def delete_stored_player_override_group(self, group_key: str):
        self.execute(
            'DELETE FROM `player_override` WHERE `group_key` = ?', (group_key,)
        )

    # ---------------------------------------------------------------------------------
    # Team overrides
    # ---------------------------------------------------------------------------------

    def _row_to_stored_team_override(
        self, row: dict[str, Any]
    ) -> StoredChampionshipTeamOverride:
        return StoredChampionshipTeamOverride(
            id=row['id'],
            event_uniq_id=row['event_uniq_id'],
            tournament_id=row['tournament_id'],
            source_team_id=row['source_team_id'],
            group_key=row['group_key'],
        )

    def load_stored_team_overrides(self) -> list[StoredChampionshipTeamOverride]:
        self.execute('SELECT * FROM `team_override` ORDER BY `id`')
        return [self._row_to_stored_team_override(row) for row in self.fetchall()]

    def set_stored_team_override(
        self, stored_override: StoredChampionshipTeamOverride
    ) -> StoredChampionshipTeamOverride:
        self.execute(
            'INSERT INTO `team_override` ('
            '   `event_uniq_id`, `tournament_id`, `source_team_id`, `group_key`'
            ') VALUES (?, ?, ?, ?) '
            'ON CONFLICT(`event_uniq_id`, `tournament_id`, `source_team_id`) '
            'DO UPDATE SET `group_key` = excluded.`group_key`',
            (
                stored_override.event_uniq_id,
                stored_override.tournament_id,
                stored_override.source_team_id,
                stored_override.group_key,
            ),
        )
        return stored_override

    def delete_stored_team_override(
        self, event_uniq_id: str, tournament_id: int, source_team_id: int
    ):
        self.execute(
            'DELETE FROM `team_override` '
            'WHERE `event_uniq_id` = ? AND `tournament_id` = ? '
            'AND `source_team_id` = ?',
            (event_uniq_id, tournament_id, source_team_id),
        )

    def delete_stored_team_override_group(self, group_key: str):
        self.execute('DELETE FROM `team_override` WHERE `group_key` = ?', (group_key,))

    # ---------------------------------------------------------------------------------
    # Championship rules
    # ---------------------------------------------------------------------------------

    def _row_to_stored_championship_rule(
        self, row: dict[str, Any]
    ) -> StoredChampionshipRule:
        return StoredChampionshipRule(
            id=row['id'],
            index=row['index'],
            type=row['type'],
            best_n=row['best_n'],
            options=self.load_json_from_database_field(row['options'], {}),
        )

    def load_stored_championship_rules(self) -> list[StoredChampionshipRule]:
        self.execute('SELECT * FROM `championship_rule` ORDER BY `index`, `id`')
        return [self._row_to_stored_championship_rule(row) for row in self.fetchall()]

    def replace_stored_championship_rules(
        self, stored_rules: list[StoredChampionshipRule]
    ):
        """Replace the whole ordered rule list (the config is edited as a
        list, so it is simplest to rewrite it wholesale)."""
        self.execute('DELETE FROM `championship_rule`')
        for index, stored_rule in enumerate(stored_rules):
            self.execute(
                'INSERT INTO `championship_rule` '
                '(`index`, `type`, `best_n`, `options`) VALUES (?, ?, ?, ?)',
                (
                    index,
                    stored_rule.type,
                    stored_rule.best_n,
                    self.dump_to_json_database_field(stored_rule.options, {}),
                ),
            )

    def add_stored_championship_rule(
        self, stored_rule: StoredChampionshipRule
    ) -> StoredChampionshipRule:
        self.execute(
            'INSERT INTO `championship_rule` '
            '(`index`, `type`, `best_n`, `options`) VALUES (?, ?, ?, ?)',
            (
                stored_rule.index,
                stored_rule.type,
                stored_rule.best_n,
                self.dump_to_json_database_field(stored_rule.options, {}),
            ),
        )
        stored_rule.id = self._last_inserted_id()
        return stored_rule

    def update_stored_championship_rule(
        self, stored_rule: StoredChampionshipRule
    ) -> StoredChampionshipRule:
        self.execute(
            'UPDATE `championship_rule` '
            'SET `type` = ?, `best_n` = ?, `options` = ? WHERE `id` = ?',
            (
                stored_rule.type,
                stored_rule.best_n,
                self.dump_to_json_database_field(stored_rule.options, {}),
                stored_rule.id,
            ),
        )
        return stored_rule

    def delete_stored_championship_rule(self, rule_id: int):
        self.execute('DELETE FROM `championship_rule` WHERE `id` = ?', (rule_id,))

    def reorder_stored_championship_rules(self, rule_ids: list[int]):
        existing_ids = [rule.id for rule in self.load_stored_championship_rules()]
        if len(rule_ids) != len(existing_ids) or set(rule_ids) != set(existing_ids):
            raise ValueError('Rule order does not match the stored rules')
        for index, rule_id in enumerate(rule_ids):
            self.execute(
                'UPDATE `championship_rule` SET `index` = ? WHERE `id` = ?',
                (index, rule_id),
            )

    def load_stored_manual_tiebreaks(self) -> dict[str, int]:
        self.execute('SELECT * FROM `championship_manual_tiebreak`')
        return {row['competitor_key']: row['position'] for row in self.fetchall()}

    def set_stored_manual_tiebreaks(self, updates: dict[str, int | None]):
        """Upsert a position for each competitor key, or clear it (None)."""
        for competitor_key, position in updates.items():
            if position is None:
                self.execute(
                    'DELETE FROM `championship_manual_tiebreak` '
                    'WHERE `competitor_key` = ?',
                    (competitor_key,),
                )
            else:
                self.execute(
                    'INSERT INTO `championship_manual_tiebreak` '
                    '(`competitor_key`, `position`) VALUES (?, ?) '
                    'ON CONFLICT(`competitor_key`) DO UPDATE SET `position` = ?',
                    (competitor_key, position, position),
                )

    def delete_stored_manual_tiebreaks(self):
        self.execute('DELETE FROM `championship_manual_tiebreak`')

    def rename_event_references(self, old_event_uniq_id: str, new_event_uniq_id: str):
        """Repoint every reference to a renamed event (its sources and the
        identity overrides that pin its players/teams)."""
        for table in ('source', 'player_override', 'team_override'):
            self.execute(
                f'UPDATE `{table}` SET `event_uniq_id` = ? '  # noqa: S608
                'WHERE `event_uniq_id` = ?',
                (new_event_uniq_id, old_event_uniq_id),
            )

    # ---------------------------------------------------------------------------------
    # Championship categories
    # ---------------------------------------------------------------------------------

    def _row_to_stored_championship_criterion(
        self, row: dict[str, Any]
    ) -> StoredChampionshipCriterion:
        return StoredChampionshipCriterion(
            id=row['id'],
            championship_category_id=row['championship_category_id'],
            type=row['type'],
            options=self.load_json_from_database_field(row['options']),
        )

    def load_stored_championship_criteria(
        self, championship_category_id: int
    ) -> list[StoredChampionshipCriterion]:
        self.execute(
            'SELECT * FROM `championship_criterion` '
            'WHERE `championship_category_id` = ? ORDER BY `id`',
            (championship_category_id,),
        )
        return [
            self._row_to_stored_championship_criterion(row) for row in self.fetchall()
        ]

    def _row_to_stored_championship_category(
        self, row: dict[str, Any]
    ) -> StoredChampionshipCategory:
        category = StoredChampionshipCategory(
            id=row['id'],
            name=row['name'],
            index=row['index'],
        )
        category.stored_criteria = self.load_stored_championship_criteria(row['id'])
        return category

    def load_stored_championship_categories(
        self,
    ) -> list[StoredChampionshipCategory]:
        self.execute('SELECT * FROM `championship_category` ORDER BY `index`, `id`')
        return [
            self._row_to_stored_championship_category(row) for row in self.fetchall()
        ]

    def replace_stored_championship_categories(
        self, stored_categories: list[StoredChampionshipCategory]
    ):
        """Replace categories and their criteria as one ordered config."""
        self.execute('DELETE FROM `championship_category`')
        for index, stored_category in enumerate(stored_categories):
            self.execute(
                'INSERT INTO `championship_category` (`name`, `index`) VALUES (?, ?)',
                (stored_category.name, index),
            )
            category_id = self._last_inserted_id()
            stored_category.id = category_id
            for stored_criterion in stored_category.stored_criteria:
                self.execute(
                    'INSERT INTO `championship_criterion` ('
                    '    `championship_category_id`, `type`, `options`'
                    ') VALUES (?, ?, ?)',
                    (
                        category_id,
                        stored_criterion.type,
                        self.dump_to_json_database_field(stored_criterion.options, {}),
                    ),
                )
                stored_criterion.id = self._last_inserted_id()
                stored_criterion.championship_category_id = category_id

    def add_stored_championship_category(
        self, stored_category: StoredChampionshipCategory
    ) -> StoredChampionshipCategory:
        self.execute(
            'INSERT INTO `championship_category` (`name`, `index`) VALUES (?, ?)',
            (stored_category.name, stored_category.index),
        )
        stored_category.id = self._last_inserted_id()
        for stored_criterion in stored_category.stored_criteria:
            stored_criterion.championship_category_id = stored_category.id
            self.add_stored_championship_criterion(stored_criterion)
        return stored_category

    def rename_stored_championship_category(self, category_id: int, name: str):
        self.execute(
            'UPDATE `championship_category` SET `name` = ? WHERE `id` = ?',
            (name, category_id),
        )

    def delete_stored_championship_category(self, category_id: int):
        self.execute(
            'DELETE FROM `championship_category` WHERE `id` = ?', (category_id,)
        )

    def reorder_stored_championship_categories(self, category_ids: list[int]):
        existing_categories = self.load_stored_championship_categories()
        existing_ids = [category.id for category in existing_categories]
        if len(category_ids) != len(existing_ids) or set(category_ids) != set(
            existing_ids
        ):
            raise ValueError('Category order does not match the stored categories')
        for index, category_id in enumerate(category_ids):
            self.execute(
                'UPDATE `championship_category` SET `index` = ? WHERE `id` = ?',
                (index, category_id),
            )

    def add_stored_championship_criterion(
        self, stored_criterion: StoredChampionshipCriterion
    ) -> StoredChampionshipCriterion:
        self.execute(
            'INSERT INTO `championship_criterion` ('
            '    `championship_category_id`, `type`, `options`'
            ') VALUES (?, ?, ?)',
            (
                stored_criterion.championship_category_id,
                stored_criterion.type,
                self.dump_to_json_database_field(stored_criterion.options, {}),
            ),
        )
        stored_criterion.id = self._last_inserted_id()
        return stored_criterion

    def update_stored_championship_criterion(
        self, stored_criterion: StoredChampionshipCriterion
    ) -> StoredChampionshipCriterion:
        self.execute(
            'UPDATE `championship_criterion` SET `type` = ?, `options` = ? '
            'WHERE `id` = ? AND `championship_category_id` = ?',
            (
                stored_criterion.type,
                self.dump_to_json_database_field(stored_criterion.options, {}),
                stored_criterion.id,
                stored_criterion.championship_category_id,
            ),
        )
        return stored_criterion

    def delete_stored_championship_criterion(self, category_id: int, criterion_id: int):
        self.execute(
            'DELETE FROM `championship_criterion` '
            'WHERE `id` = ? AND `championship_category_id` = ?',
            (criterion_id, category_id),
        )
