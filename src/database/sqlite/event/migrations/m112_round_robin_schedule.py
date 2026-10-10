from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The schedule of a round-robin, defined for the whole tournament
    before it starts: who meets whom, with which colours, in every round.

    ``round_robin_schedule`` is the saved schedule, which the pairings are
    made from, and ``round_robin_schedule_draft`` the one the arbiter is
    editing, kept until they save or cancel it."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `round_robin_schedule` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `round_robin_schedule_draft` TEXT'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `round_robin_schedule_draft`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `round_robin_schedule`'
        )
