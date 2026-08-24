from abc import ABC, abstractmethod

from common.i18n import _


class TieBreakCategory(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the category. Used to group the tie-breaks in the select."""


class PlayerRecordCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _("Player's record")


class OpponentRecordCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _("Opponents' records")


class RatingCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _('Ratings')


class OtherCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _('Others')


class TeamScoreCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _("Team's score")


class TeamOpponentRecordCategory(TieBreakCategory):
    @property
    def name(self) -> str:
        return _("Team opponents' records")
