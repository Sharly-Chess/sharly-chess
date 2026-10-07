from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Replaces the hard / soft flag of the prohibited pairings with a
    constraint, so that a soft group can also be avoided as the pairing
    engine's lowest-priority criterion, and the automatic grouping can be
    turned off without forgetting its attribute."""

    def forward(self) -> None:
        for table, column, new_column in (
            (
                'tournament',
                'prohibited_pairing_dimension_is_hard',
                'prohibited_pairing_dimension_constraint',
            ),
            ('prohibited_pairing_group', 'is_hard', 'constraint_type'),
        ):
            self.database.execute(
                f"ALTER TABLE `{table}` ADD `{new_column}` TEXT NOT NULL DEFAULT 'HARD'"
            )
            self.database.execute(
                f'UPDATE `{table}` SET `{new_column}` = '
                f"CASE WHEN `{column}` THEN 'HARD' ELSE 'PROTECT_TOP' END"
            )
            self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `{column}`')

    def backward(self) -> None:
        for table, column, new_column in (
            (
                'tournament',
                'prohibited_pairing_dimension_is_hard',
                'prohibited_pairing_dimension_constraint',
            ),
            ('prohibited_pairing_group', 'is_hard', 'constraint_type'),
        ):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `{column}` INTEGER NOT NULL DEFAULT 1'
            )
            self.database.execute(
                f"UPDATE `{table}` SET `{column}` = `{new_column}` IN ('HARD', 'NONE')"
            )
            self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `{new_column}`')
