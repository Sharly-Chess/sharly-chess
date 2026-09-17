from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `client_controller` RENAME TO `display_controller`'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `display_controller` RENAME TO `client_controller`'
        )
