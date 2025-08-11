from pathlib import Path

from database.sqlite.migration import BaseMigration, PostUpgradeTask


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('SELECT `path` FROM `info`')
        event_path = self.database.fetchone()['path'] or 'papi'
        self.database.execute('SELECT * FROM `tournament`')
        for row in self.database.fetchall():
            path = Path(row['path'] or event_path)
            filename = row['filename'] or row['uniq_id']
            file = path / f'{filename}.papi'
            if file.exists():
                self.post_upgrade_tasks.append(
                    PostUpgradeTask(
                        function=self.import_papi_file, args=[row['id'], file]
                    )
                )
            else:
                fields = {
                    'pairing': 'SWISS_STANDARD',
                    'rounds': 7,
                    'rating': 1,
                }
                field_sets = ', '.join(f'`{field_}` = ?' for field_ in fields)
                self.database.execute(
                    f'UPDATE `tournament` SET {field_sets} WHERE `id` = ?',
                    tuple(fields.values()) + (row['id'],),
                )

        self.database.execute('ALTER TABLE `info` DROP COLUMN `path`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `path`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `filename`')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `last_pairing_update` '
            'FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `last_player_update` '
            'FLOAT NOT NULL DEFAULT 0.0'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` ADD `path` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `path` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `filename` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_player_update`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_pairing_update`'
        )

    def import_papi_file(self, tournament_id: int, papi_file_path: Path):
        from common import get_logger
        from common.exception import SharlyChessException
        from common.i18n import _
        from data.loader import EventLoader
        from plugins.ffe.ffe_tournament_importers import PapiTournamentImporter

        logger = get_logger()

        event = EventLoader().load_event(self.database.file.stem)
        tournament = event.tournaments_by_id[tournament_id]
        try:
            PapiTournamentImporter().load_tournament(papi_file_path, event, tournament)
            logger.info(
                tournament.log_prefix
                + _('Papi file [{file}] successfully imported.').format(
                    file=papi_file_path
                )
            )
        except SharlyChessException as error:
            logger.error(
                tournament.log_prefix
                + _('Import of papi file [{file}] failed.').format(file=papi_file_path)
                + '\n'
                + _('{string}: {value}').format(string=_('Error'), value=error)
                + '\n'
                + _(
                    'You can try again from the tournament card '
                    '(Actions > Import > Papi file).'
                )
            )
