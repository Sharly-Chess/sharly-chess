from typing import override

from data.screens.screen_types import (
    BoardsScreenType,
    CheckInScreenType,
    ImageScreenType,
    InputScreenType,
    PlayersScreenType,
    RankingScreenType,
    ResultsScreenType,
    ScreenType,
)
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class ScreenTypeManager(EventBoundEntityManager[ScreenType]):
    @override
    def entity_types(self) -> list[type[ScreenType]]:
        screen_types: list[type[ScreenType]] = [
            CheckInScreenType,
            InputScreenType,
            BoardsScreenType,
            PlayersScreenType,
            ResultsScreenType,
            RankingScreenType,
            ImageScreenType,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_screen_types')(
            screen_types=screen_types
        )
        return screen_types
