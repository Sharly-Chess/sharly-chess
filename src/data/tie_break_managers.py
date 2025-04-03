import itertools

from data.tie_break import AbstractTieBreak, TIE_BREAK_CLASSES
from data.util import AbstractEntityManager
from plugins.manager import plugin_manager


class TieBreakManager(AbstractEntityManager[AbstractTieBreak]):
    """Entry class for interacting with tie-breaks"""
    @staticmethod
    def entity_types() -> list[type[AbstractTieBreak]]:
        return TIE_BREAK_CLASSES + list(itertools.chain.from_iterable(
            plugin_manager.hook.get_extra_tie_break_classes()
        ))


class PapiTieBreakManager(AbstractEntityManager[AbstractTieBreak]):
    @staticmethod
    def entity_types() -> list[type[AbstractTieBreak]]:
        return [
            tie_break_type for tie_break_type in TieBreakManager.entity_types()
            if tie_break_type().papi_id is not None
        ]

    @classmethod
    def type_by_papi_id(cls) -> dict[str, type[AbstractTieBreak]]:
        return {
            str(entity_type.static_papi_id()): entity_type
            for entity_type in cls.entity_types()
            if entity_type.static_papi_id() is not None
        }
