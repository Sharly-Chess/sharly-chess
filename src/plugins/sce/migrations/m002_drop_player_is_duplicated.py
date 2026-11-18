from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    """A player found on Sharly-Chess.com already is marked by the id of the
    registration found there. The flag that marked them before, which nothing
    clears any more, is dropped: the next synchronisation tries to create
    these players again and marks them by their registration id when they
    are still there."""

    def forward(self) -> None:
        self.database.execute(
            "UPDATE `player` SET plugin_data = JSON_REMOVE(plugin_data, '$.sce.is_duplicated') "
            "WHERE JSON_TYPE(plugin_data, '$.sce.is_duplicated') IS NOT NULL"
        )

    def backward(self) -> None:
        self.database.execute(
            "UPDATE `player` SET plugin_data = JSON_SET(plugin_data, '$.sce.is_duplicated', JSON('false')) "
            "WHERE JSON_TYPE(plugin_data, '$.sce') = 'object'"
        )
