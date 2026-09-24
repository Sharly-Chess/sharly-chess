"""A random tournament generator.

The check-list requires one alongside the checker (C.04.A Annex 3,
question 19: "Both a PTC and an RTG must be available for obtaining a
TAPC"), and describes what it must be able to vary (question 24), how it
must behave when asked twice (question 30), and what the tournaments it
writes must satisfy (question 31: "correct pairings and standings").

A tournament is built here the way the application builds one: the
players are entered, each round is paired by the pairing engine, results
are drawn from the ratings by the published statistical model, and the
standings come from the tie-break engine. Nothing about the file is
invented after the fact, so a tournament that comes out of this is one
the program stands behind -- which is what makes it worth handing to
another program's checker.

Byes and forfeits are drawn per player and per board rather than given
as counts, so a run of tournaments varies as real ones do; a rate of
0.05 means each player, each round, has that chance of a bye. Results
are drawn from the *stated* ratings, never from a hidden playing
strength: a player who is secretly stronger than their rating would gain
rating steadily across a sample, which is exactly what question 32
measures and forbids.
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from common.logger import get_logger
from data.pairings.simulation import DEFAULT_RATING, draw_result
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournament,
    StoredTournamentPlayer,
)
from utils.types import PlayerRating
from utils.enum import PlayerRatingType, Result, TournamentRating

if TYPE_CHECKING:
    from data.tournament import Tournament

logger = get_logger()

#: The unusual over-the-board results question 24 asks the generator to
#: be able to produce: a half point to one side only, or nothing to
#: either.
UNUSUAL_RESULTS = (Result.PENALTY_DL, Result.PENALTY_LD, Result.PENALTY_LL)


@dataclass(frozen=True)
class Frequency:
    """How often something happens: a fixed number of them, or the chance
    each opportunity has of being one.

    The check-list asks for each of the byes, the forfeits and the unusual
    results to be settable as a "fixed number or percentage" (question
    24), so both are accepted. Written ``4`` it is four of them in the
    whole tournament; written ``5%`` or ``0.05`` it is the chance each
    player has in each round, or each board has.
    """

    count: int | None = None
    rate: float | None = None

    @classmethod
    def parse(cls, value: str | float | None) -> 'Frequency | None':
        """``4``, ``5%`` or ``0.05``; None when nothing was asked for."""
        if value is None or value == '':
            return None
        if isinstance(value, int | float):
            return cls(rate=float(value))
        text = str(value).strip()
        if text.endswith('%'):
            return cls(rate=float(text[:-1]) / 100)
        number = float(text)
        # A whole number is a count, a fraction is a rate: 1 would be
        # ambiguous, and is read as the count, 100% being writable as such.
        if number.is_integer():
            return cls(count=int(number))
        return cls(rate=number)

    def occurrences(self, opportunities: int, chance: random.Random) -> int:
        """How many of this many opportunities are one."""
        if self.count is not None:
            return min(self.count, opportunities)
        rate = self.rate or 0.0
        return sum(1 for _ in range(opportunities) if chance.random() < rate)

    def share_over_rounds(self, rounds: int, chance: random.Random) -> list[int]:
        """A fixed number spread over the rounds; a rate leaves each round
        to draw its own, which ``None`` here stands for."""
        if self.count is None:
            return []
        shares = [0] * rounds
        for _ in range(self.count):
            shares[chance.randrange(rounds)] += 1
        return shares


#: Rates a run uses when the caller states none. Chosen per tournament
#: from these ranges rather than fixed, which question 25 asks for.
_UNSTATED_PLAYER_RANGE = (8, 120)
_UNSTATED_ROUND_RANGE = (3, 11)
_UNSTATED_RATE_RANGE = (0.0, 0.08)
_UNSTATED_TOP_RATING_RANGE = (1800, 2500)
_UNSTATED_RATING_STEP_RANGE = (2.0, 25.0)


@dataclass
class TournamentSettings:
    """What a generated tournament is made of.

    Every field may be left unset, in which case a value is drawn for it
    (question 25); what is set is honoured exactly.
    """

    players: int | None = None
    rounds: int | None = None
    #: The ratings to give the players, strongest first. Stated outright
    #: (question 27), or built from the top rating and the step below
    #: (question 28), or drawn (question 29).
    ratings: list[int] | None = None
    top_rating: int | None = None
    rating_step: float | None = None
    #: The chance each player has of each kind of bye, per round.
    full_point_byes: Frequency | None = None
    half_point_byes: Frequency | None = None
    zero_point_byes: Frequency | None = None
    #: The chance each board has of being decided by forfeit, or of
    #: carrying one of the unusual results.
    forfeit_wins: Frequency | None = None
    forfeit_losses: Frequency | None = None
    unusual_results: Frequency | None = None
    #: The Baku acceleration method.
    acceleration: bool = False
    #: The criteria the standings are ranked on, as TRF26 acronyms.
    tie_breaks: list[str] = field(default_factory=lambda: ['PTS'])
    name: str = 'Generated tournament'

    def settled(self, chance: random.Random) -> 'TournamentSettings':
        """The same settings with a value drawn for everything unstated."""

        def frequency(stated: Frequency | None) -> Frequency:
            if stated is not None:
                return stated
            return Frequency(rate=chance.uniform(*_UNSTATED_RATE_RANGE))

        players = self.players or chance.randint(*_UNSTATED_PLAYER_RANGE)
        rounds = self.rounds or chance.randint(*_UNSTATED_ROUND_RANGE)
        # More rounds than a field can fill would leave players with
        # nobody left to meet.
        rounds = max(1, min(rounds, players - 1))
        return TournamentSettings(
            players=players,
            rounds=rounds,
            ratings=self.ratings,
            top_rating=self.top_rating or chance.randint(*_UNSTATED_TOP_RATING_RANGE),
            rating_step=self.rating_step
            if self.rating_step is not None
            else chance.uniform(*_UNSTATED_RATING_STEP_RANGE),
            full_point_byes=frequency(self.full_point_byes),
            half_point_byes=frequency(self.half_point_byes),
            zero_point_byes=frequency(self.zero_point_byes),
            forfeit_wins=frequency(self.forfeit_wins),
            forfeit_losses=frequency(self.forfeit_losses),
            unusual_results=frequency(self.unusual_results),
            acceleration=self.acceleration,
            tie_breaks=list(self.tie_breaks),
            name=self.name,
        )

    def player_ratings(self, chance: random.Random) -> list[int]:
        """The rating of each player, strongest first."""
        if self.ratings:
            return list(self.ratings)
        assert self.players is not None
        assert self.top_rating is not None
        assert self.rating_step is not None
        return [
            max(1000, round(self.top_rating - index * self.rating_step))
            for index in range(self.players)
        ]


class RandomTournamentGenerator:
    """Builds a tournament round by round, with the program's own engines."""

    def __init__(self, seed: int | None = None) -> None:
        #: Stated to reproduce a tournament, drawn otherwise: asked twice
        #: without one, the generator must not answer the same twice
        #: (question 30).
        self.seed = random.randrange(2**32) if seed is None else seed
        self.chance = random.Random(self.seed)

    def generate(self, settings: TournamentSettings, uniq_id: str) -> int:
        """Build one tournament into the event ``uniq_id`` and return its id."""
        from data.input_output.trf.trf_importer import TrfTournamentImporter
        from data.loader import EventLoader
        from data.pairings.acceleration import BakuSwissVariation
        from data.pairings.variations import StandardSwissVariation

        settled = settings.settled(self.chance)
        assert settled.players is not None and settled.rounds is not None
        variation = (
            BakuSwissVariation() if settled.acceleration else StandardSwissVariation()
        )
        with EventDatabase(uniq_id, write=True) as database:
            tournament_id = database.add_stored_tournament(
                StoredTournament(
                    id=None,
                    name=settled.name,
                    pairing=variation.id,
                    rounds=settled.rounds,
                    # The standard rating of each player, which is the
                    # rating the file states and the one the results are
                    # drawn from.
                    rating=TournamentRating.STANDARD.value,
                    player_rating_type=PlayerRatingType.FIDE.value,
                )
            )
            for number, rating in enumerate(
                settled.player_ratings(self.chance), start=1
            ):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'Player{number:04d}',
                        first_name='Test',
                        ratings={
                            TournamentRating.STANDARD.value: PlayerRating(
                                fide=rating
                            ).stored_value,
                        },
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=number,
                    )
                )

        event = EventLoader().load_event(uniq_id)
        tie_breaks, unknown = TrfTournamentImporter.read_tie_breaks(
            settled.tie_breaks, event
        )
        if unknown:
            raise ValueError(f'Unknown tie-breaks: {", ".join(unknown)}')
        with EventDatabase(uniq_id, write=True) as database:
            database.delete_all_tournament_stored_tie_breaks(tournament_id)
            for index, tie_break in enumerate(tie_breaks):
                stored = tie_break.to_stored_value()
                stored.tournament_id = tournament_id
                stored.index = index
                database.add_stored_tie_break(stored)

        # A frequency given as a fixed number is shared over the rounds
        # before the tournament starts, so the whole of it is used; a rate
        # leaves each round to draw its own.
        self._planned = {
            name: getattr(settled, name).share_over_rounds(settled.rounds, self.chance)
            for name in (
                'full_point_byes',
                'half_point_byes',
                'zero_point_byes',
                'forfeit_wins',
                'forfeit_losses',
                'unusual_results',
            )
        }
        for round_ in range(1, settled.rounds + 1):
            self._play_round(uniq_id, tournament_id, round_, settled)
        return tournament_id

    def _this_round(self, name: str, round_: int) -> int | None:
        """How many of a planned number fall in this round, or None when
        the frequency was a rate and each opportunity draws its own."""
        shares = self._planned.get(name) or []
        return shares[round_ - 1] if shares else None

    def _tournament(self, uniq_id: str, tournament_id: int) -> 'Tournament':
        from data.loader import EventLoader

        EventLoader.unload_event(uniq_id)
        # The event has to be held for as long as the tournament is read.
        self._event = EventLoader().load_event(uniq_id)
        return self._event.tournaments_by_id[tournament_id]

    def _play_round(
        self,
        uniq_id: str,
        tournament_id: int,
        round_: int,
        settings: TournamentSettings,
    ) -> None:
        tournament = self._tournament(uniq_id, tournament_id)
        self._give_byes(tournament, round_, settings)
        tournament = self._tournament(uniq_id, tournament_id)
        error = tournament.generate_round_pairings(round_)
        if error:
            raise ValueError(f'round {round_}: {error}')
        tournament = self._tournament(uniq_id, tournament_id)
        self._enter_results(tournament, round_, settings)

    def _give_byes(
        self, tournament: 'Tournament', round_: int, settings: TournamentSettings
    ) -> None:
        """Each player's chance of sitting this round out."""
        kinds = (
            ('full_point_byes', Result.FULL_POINT_BYE),
            ('half_point_byes', Result.HALF_POINT_BYE),
            ('zero_point_byes', Result.ZERO_POINT_BYE),
        )
        free = list(tournament.tournament_players)
        self.chance.shuffle(free)
        for name, result in kinds:
            frequency = getattr(settings, name)
            planned = self._this_round(name, round_)
            taking = (
                planned
                if planned is not None
                else frequency.occurrences(len(free), self.chance)
            )
            for player in free[:taking]:
                tournament.set_player_byes(player, {round_: result})
            free = free[taking:]

    def _enter_results(
        self, tournament: 'Tournament', round_: int, settings: TournamentSettings
    ) -> None:
        """One result per board, drawn from the two ratings."""
        played = [
            board
            for board in tournament.get_round_boards(round_)
            # A player left over by an odd field already holds the bye the
            # pairing system gives them.
            if board.black_tournament_player is not None
        ]
        order = list(played)
        self.chance.shuffle(order)
        decided: dict[int, Result] = {}
        for name, result in (
            ('forfeit_wins', Result.FORFEIT_WIN),
            ('forfeit_losses', Result.FORFEIT_LOSS),
            ('unusual_results', None),
        ):
            frequency = getattr(settings, name)
            planned = self._this_round(name, round_)
            taking = (
                planned
                if planned is not None
                else frequency.occurrences(len(order), self.chance)
            )
            for board in order[:taking]:
                decided[board.id] = (
                    result
                    if result is not None
                    else self.chance.choice(UNUSUAL_RESULTS)
                )
            order = order[taking:]
        for board in played:
            black = board.black_tournament_player
            assert black is not None, 'boards without an opponent were left out'
            tournament.add_result(
                board,
                decided.get(board.id)
                or draw_result(
                    board.white_tournament_player.rating or DEFAULT_RATING,
                    black.rating or DEFAULT_RATING,
                    self.chance,
                ),
            )


def generate_tournament_file(
    settings: TournamentSettings,
    output_file: Path,
    seed: int | None = None,
) -> int:
    """Generate one tournament and write it as TRF26. Returns the seed it
    was built from, so the same tournament can be asked for again."""
    from data.input_output.tournament_exporters import Trf26TournamentExporter
    from data.loader import EventLoader

    generator = RandomTournamentGenerator(seed)
    uniq_id = EventLoader().get_unused_event_uniq_id('generator')
    EventDatabase(uniq_id).create()
    try:
        tournament_id = generator.generate(settings, uniq_id)
        EventLoader.unload_event(uniq_id)
        event = EventLoader().load_event(uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        exporter = Trf26TournamentExporter()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding=exporter.file_encoding) as file:
            exporter.dump_to_file(file, tournament)
    finally:
        EventDatabase(uniq_id).file.unlink(missing_ok=True)
    return generator.seed
