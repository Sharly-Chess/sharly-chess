from common.papi_web_config import PapiWebConfig
from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `info` ADD `hide_background_image` INTEGER'
        )
        self._execute(
            'UPDATE `info` SET `hide_background_image` = ?',
            (1 if PapiWebConfig.default_hide_background_image else 0,),
        )
