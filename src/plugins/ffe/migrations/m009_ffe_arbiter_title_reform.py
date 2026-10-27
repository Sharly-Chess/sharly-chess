from typing import ClassVar

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Converts the FFE arbiter titles to the 2026 reform, following the transition
    rules of the DNA. The Elite titles are replaced by the FIDE titles they correspond
    to, unless the account already has a FIDE arbiter title."""

    TITLE_MAPPING: ClassVar[dict[str, str]] = {
        'AS': '',
        'AFJ': 'AFJ',
        'AFC': 'AFM',
        'AFO1': 'AFO',
        'AFO2': 'AFO',
        'AFE1': 'AFO',
        'AFE2': 'AFO',
    }

    FIDE_TITLE_MAPPING: ClassVar[dict[str, str]] = {
        'AFE1': 'FA',
        'AFE2': 'IA',
    }

    def forward(self) -> None:
        for old_title, fide_title in self.FIDE_TITLE_MAPPING.items():
            self.database.execute(
                'UPDATE `account` SET `fide_arbiter_title` = ? '
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_arbiter_title') = ? "
                "AND COALESCE(`fide_arbiter_title`, '') = '';",
                (fide_title, old_title),
            )
        for old_title, title in self.TITLE_MAPPING.items():
            self.database.execute(
                'UPDATE `account` SET plugin_data = JSON_SET('
                "plugin_data, '$.ffe.ffe_arbiter_title', ?"
                ") WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_arbiter_title') = ?;",
                (title, old_title),
            )

    def backward(self) -> None:
        for old_title, title in (('AFM', 'AFC'), ('AFO', 'AFO1')):
            self.database.execute(
                'UPDATE `account` SET plugin_data = JSON_SET('
                "plugin_data, '$.ffe.ffe_arbiter_title', ?"
                ") WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_arbiter_title') = ?;",
                (title, old_title),
            )
