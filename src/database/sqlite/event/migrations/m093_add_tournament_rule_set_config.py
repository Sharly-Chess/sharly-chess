import json

from database.sqlite.migration import BaseMigration

# The no-round-3-protection variants are replaced by the fields of the
# standard rule sets: the Loubatière drops the protection in phase 3 (which
# qualifies a single team per group), the Parité in a phase 2 the Coupe
# direction gave a single qualifying place, the women's championship in the
# N2F second phase (which promotes to the N1F). All keep the 3 rounds they
# had, so tournaments pair as before.
_NO_R3_REPLACEMENTS: tuple[tuple[str, str, dict], ...] = (
    (
        'ffe-coupe-jean-claude-loubatiere-no-r3',
        'ffe-coupe-jean-claude-loubatiere',
        {'phase': 'phase-3'},
    ),
    (
        'ffe-coupe-de-la-parite-no-r3',
        'ffe-coupe-de-la-parite',
        {'phase': 'phase-2', 'single_qualifier': True},
    ),
    (
        'ffe-championnat-feminin-n1-n2-no-r3',
        'ffe-championnat-feminin-n1-n2',
        {'division': 'n2f-phase-2'},
    ),
)

# The women's championship applied the round-3 restriction and the
# same-club avoidance to every division; only the N2F zone phase does now.
# Existing tournaments are pinned to that division so they keep pairing as
# they did — the arbiter re-picks their real division if it differs.
_FEMININ_RULE_SET = 'ffe-championnat-feminin-n1-n2'
_FEMININ_LEGACY_CONFIG = {'division': 'n2f-zone'}


class Migration(BaseMigration):
    """Adds `rule_set_config` to tournaments: the JSON values of the form
    fields a rule set contributes, keyed by field id. Only the rule set
    interprets them."""

    def forward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `rule_set_config` TEXT')
        self.database.execute(
            'UPDATE `tournament` SET `rule_set_config` = ? WHERE `rule_set` = ?',
            (json.dumps(_FEMININ_LEGACY_CONFIG), _FEMININ_RULE_SET),
        )
        for old_rule_set, rule_set, config in _NO_R3_REPLACEMENTS:
            self.database.execute(
                'UPDATE `tournament` SET `rule_set` = ?, `rule_set_config` = ? '
                'WHERE `rule_set` = ?',
                (rule_set, json.dumps(config), old_rule_set),
            )

    def backward(self):
        for old_rule_set, rule_set, config in _NO_R3_REPLACEMENTS:
            self.database.execute(
                'UPDATE `tournament` SET `rule_set` = ? '
                'WHERE `rule_set` = ? AND `rule_set_config` = ?',
                (old_rule_set, rule_set, json.dumps(config)),
            )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `rule_set_config`')
