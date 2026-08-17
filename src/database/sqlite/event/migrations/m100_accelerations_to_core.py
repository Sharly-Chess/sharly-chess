import json

from database.sqlite.migration import BaseMigration

# The accelerated pairing variations and their settings used to be
# provided by the `pairing_acceleration` plugin, which namespaced every
# id with this prefix. They now live in the core, with plain ids, so the
# prefix is stripped from the stored tournament pairing and settings.
PREFIX = 'pairing_acceleration-'

# Core acceleration ids, used to put the prefix back on a downgrade.
_VARIATION_IDS = {
    'SWISS_BAKU',
    'SWISS_HALEY',
    'SWISS_HALEY_SOFT',
    'SWISS_PROGRESSIVE',
    'SWISS_CUSTOM',
    'SWISS_INITIAL_SCORE',
}
_SETTING_IDS = {
    'GROUP_A_2',
    'GROUP_B_2',
    'GROUP_A_3',
    'GROUP_B_3',
    'GROUP_C_3',
    'CUSTOM_ACCELERATION',
    'INITIAL_PAIRING_SCORE',
}
# The FFE "Niçois" variation stayed a plugin one, but its id was built on
# top of the plugin prefix (`ffe-pairing_acceleration-SWISS_NICOIS`).
_NICOIS = 'ffe-SWISS_NICOIS'
_NICOIS_LEGACY = f'ffe-{PREFIX}SWISS_NICOIS'


class Migration(BaseMigration):
    def forward(self):
        for tournament_id, pairing, settings in self._read_tournaments():
            pairing = pairing.replace(PREFIX, '')
            settings = {
                key.replace(PREFIX, ''): value for key, value in settings.items()
            }
            self._write_tournament(tournament_id, pairing, settings)
        self._rewrite_enabled_plugins(
            lambda plugins: [
                plugin for plugin in plugins if plugin != 'pairing_acceleration'
            ]
        )

    def backward(self):
        for tournament_id, pairing, settings in self._read_tournaments():
            if pairing in _VARIATION_IDS:
                pairing = f'{PREFIX}{pairing}'
            elif pairing == _NICOIS:
                pairing = _NICOIS_LEGACY
            settings = {
                (f'{PREFIX}{key}' if key in _SETTING_IDS else key): value
                for key, value in settings.items()
            }
            self._write_tournament(tournament_id, pairing, settings)
        self._rewrite_enabled_plugins(
            lambda plugins: (
                plugins
                if 'pairing_acceleration' in plugins
                else [*plugins, 'pairing_acceleration']
            )
        )

    def _read_tournaments(self) -> list[tuple[int, str, dict]]:
        self.database.execute(
            'SELECT `id`, `pairing`, `pairing_settings` FROM `tournament`'
        )
        return [
            (
                row['id'],
                row['pairing'] or '',
                json.loads(row['pairing_settings']) if row['pairing_settings'] else {},
            )
            for row in self.database.fetchall()
        ]

    def _write_tournament(self, tournament_id: int, pairing: str, settings: dict):
        self.database.execute(
            'UPDATE `tournament` SET `pairing` = ?, `pairing_settings` = ? '
            'WHERE `id` = ?',
            (pairing, json.dumps(settings), tournament_id),
        )

    def _rewrite_enabled_plugins(self, transform):
        self.database.execute('SELECT `enabled_plugins` FROM `info`')
        row = self.database.fetchone()
        if not row.get('enabled_plugins'):
            return
        plugins = transform(json.loads(row['enabled_plugins']))
        self.database.execute(
            'UPDATE `info` SET `enabled_plugins` = ?', (json.dumps(plugins),)
        )
