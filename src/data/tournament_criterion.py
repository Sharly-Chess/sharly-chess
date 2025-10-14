import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING


from data.criteria.managers import PlayerFilter, PlayerFilterManager
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournamentCriterion

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
        self.player_filter = self._get_player_filter()

    def _get_player_filter(self) -> PlayerFilter:
        filter_type = PlayerFilterManager().get_type(
            self.stored_tournament_criterion.type
        )
        options = []
        for option in filter_type.default_options():
            value = self.stored_tournament_criterion.options.get(
                option.id, option.default_value
            )
            options.append(type(option)(value))
        return filter_type(options)

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Tournameent has been garbage collected')
        return tournament

    @property
    def id(self) -> int:
        assert self.stored_tournament_criterion.id is not None
        return self.stored_tournament_criterion.id

    @property
    def name(self) -> str:
        return str(self.player_filter)

    def update(self):
        with EventDatabase(self.tournament.event.uniq_id, write=True) as database:
            database.update_stored_tournament_criterion(
                self.stored_tournament_criterion
            )
        self.player_filter = self._get_player_filter()
