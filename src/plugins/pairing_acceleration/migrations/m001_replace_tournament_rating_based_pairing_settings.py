from database.sqlite.migration import PostUpgradeTask
from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.post_upgrade_tasks.append(
            PostUpgradeTask(self._replace_tournament_rating_based_pairing_settings)
        )

    def backward(self):
        pass

    def _replace_tournament_rating_based_pairing_settings(self):
        from data.loader import EventLoader
        from plugins.pairing_acceleration.utils import PairingAccelerationUtils

        event = EventLoader().load_event(self.database.file.stem)
        for tournament in event.tournaments:
            stored_settings = tournament.stored_pairing_settings
            rating_threshold: int | None = stored_settings.get(
                'pairing_acceleration-rating_limit', None
            )
            if rating_threshold:
                PairingAccelerationUtils.set_pairing_settings_from_rating_threshold(
                    tournament, rating_threshold
                )
            dual_rating_thresholds: tuple[int, int] | None = stored_settings.get(
                'pairing_acceleration-dual_rating_limits', None
            )
            if dual_rating_thresholds:
                PairingAccelerationUtils.set_pairing_settings_from_dual_rating_thresholds(
                    tournament,
                    lower_rating_threshold=dual_rating_thresholds[0],
                    upper_rating_threshold=dual_rating_thresholds[1],
                )
