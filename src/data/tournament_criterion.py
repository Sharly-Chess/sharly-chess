import weakref
from _weakref import ReferenceType
from functools import cached_property
from typing import TYPE_CHECKING


from data.criteria.managers import PlayerFilter, TournamentPlayerFilterManager
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournamentCriterion
from utils import Utils

if TYPE_CHECKING:
    from data.tournament import Tournament


class TournamentCriterion:
    def __init__(
        self,
        tournament: 'Tournament',
        stored_tournament_criterion: StoredTournamentCriterion,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_tournament_criterion = stored_tournament_criterion

    @cached_property
    def player_filter(self) -> PlayerFilter:
        filter_type = TournamentPlayerFilterManager(self.tournament.event).get_type(
            self.stored_tournament_criterion.type
        )
        options = []
        for option in filter_type().default_options():
            value = self.stored_tournament_criterion.options.get(
                option.id, option.default_value
            )
            options.append(type(option)(value))
        return filter_type(options)

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Tournament has been garbage collected')
        return tournament

    @property
    def id(self) -> int:
        assert self.stored_tournament_criterion.id is not None
        return self.stored_tournament_criterion.id

    @property
    def name(self) -> str:
        return self.player_filter.full_name(self.tournament)

    def update(self):
        with EventDatabase(self.tournament.event.uniq_id, write=True) as database:
            database.update_stored_tournament_criterion(
                self.stored_tournament_criterion
            )
        Utils.reset_cached_properties(self, 'player_filter')
