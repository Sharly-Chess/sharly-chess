"""A random tournament generator.

The check-list requires one alongside the checker (C.04.A Annex 3,
question 19: "Both a PTC and an RTG must be available for obtaining a
TAPC"), and describes what it must be able to vary (question 24), how it
must behave when asked twice (question 30), and what the tournaments it
writes must satisfy (question 31: "correct pairings and standings").

A tournament is built here the way the application builds one: the
players are entered, each round is paired by the pairing engine, results
are drawn from the ratings (see ``simulation``), and the
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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from common.i18n import _
from common.logger import get_logger
from data.pairings.simulation import DEFAULT_RATING, draw_result
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournament,
    StoredTournamentPlayer,
)
from utils.types import PlayerRating
from utils.enum import (
    EventType,
    PlayerRatingType,
    Result,
    ScoreType,
    TeamByeType,
    TeamColourType,
    TournamentRating,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from data.pairings.variations import PairingVariation
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
        for _share in range(self.count):
            shares[chance.randrange(rounds)] += 1
        return shares


#: Rates a run uses when the caller states none. Chosen per tournament
#: from these ranges rather than fixed, which question 25 asks for.
_UNSTATED_PLAYER_RANGE = (8, 120)
_UNSTATED_ROUND_RANGE = (3, 11)
_UNSTATED_RATE_RANGE = (0.0, 0.08)
_UNSTATED_TOP_RATING_RANGE = (1800, 2500)
_UNSTATED_RATING_STEP_RANGE = (2.0, 25.0)
_UNSTATED_TEAM_RANGE = (4, 24)
_UNSTATED_TEAM_PLAYER_RANGE = (2, 6)
_UNSTATED_TIE_BREAK_COUNT_RANGE = (1, 3)

#: Every tie-break of the individual column of *Mandatory Tie-Breaks*, the
#: list an endorsed program must implement. `KS/Lx` takes "any reasonable
#: value" of the `/L±n` form, so it stands here as `KS/L+1`.
MANDATORY_INDIVIDUAL_TIE_BREAKS = (
    'DE', 'DE/P', 'BPG', 'BWG', 'REP',
    'SB', 'SB/C1', 'SB/C2', 'SB/P', 'SB/C1/P', 'SB/C2/P',
    'ARO', 'ARO/C1', 'ARO/C2', 'ARO/M1', 'ARO/M2',
    'TPR', 'PTP', 'APRO', 'APPO',
    'WIN', 'WON',
    'PS', 'PS/C1', 'PS/C2',
    'BH', 'BH/C1', 'BH/C2', 'BH/P', 'BH/M1', 'BH/M2',
    'BH/C1/P', 'BH/C2/P', 'BH/M1/P', 'BH/M2/P',
    'FB', 'FB/C1', 'FB/C2', 'FB/M1', 'FB/M2', 'FB/P',
    'FB/C1/P', 'FB/C2/P', 'FB/M1/P', 'FB/M2/P',
    'AOB', 'AOB/F',
    'KS', 'KS/L+1',
)  # fmt: skip

#: Every tie-break of the team column of *Mandatory Tie-Breaks*. `Kx` and
#: `Lx` take "any reasonable value" and stand here as `K4` and `L+1`.
MANDATORY_TEAM_TIE_BREAKS = (
    'WIN:MP', 'WON:MP',
    'PS:MP', 'PS:GP', 'PS:MP/C1', 'PS:MP/C2', 'PS:GP/C1', 'PS:GP/C2',
    'BH:MP', 'BH:GP', 'BH:MP/C1', 'BH:MP/C2', 'BH:MP/M1', 'BH:MP/M2',
    'BH:GP/C1', 'BH:GP/C2', 'BH:GP/M1', 'BH:GP/M2', 'BH:MP/P', 'BH:GP/P',
    'BH:MP/C1/P', 'BH:MP/C2/P', 'BH:MP/M1/P', 'BH:MP/M2/P',
    'BH:GP/C1/P', 'BH:GP/C2/P', 'BH:GP/M1/P', 'BH:GP/M2/P',
    'FB:MP', 'FB:GP', 'FB:MP/C1', 'FB:MP/C2', 'FB:MP/M1', 'FB:MP/M2',
    'FB:GP/C1', 'FB:GP/C2', 'FB:GP/M1', 'FB:GP/M2', 'FB:MP/P', 'FB:GP/P',
    'FB:MP/C1/P', 'FB:MP/C2/P', 'FB:MP/M1/P', 'FB:MP/M2/P',
    'FB:GP/C1/P', 'FB:GP/C2/P', 'FB:GP/M1/P', 'FB:GP/M2/P',
    'AOB:MP', 'AOB:GP', 'AOB:MP/F', 'AOB:GP/F',
    'KS:MP', 'KS:GP', 'KS:MP/L+1', 'KS:GP/L+1',
    'BC', 'TBR', 'BBE', 'MPvGP',
    'EMMSB', 'EMMSB/C1', 'EMMSB/C2', 'EMMSB/P', 'EMMSB/C1/P', 'EMMSB/C2/P',
    'EMGSB', 'EMGSB/C1', 'EMGSB/C2', 'EMGSB/P', 'EMGSB/C1/P', 'EMGSB/C2/P',
    'EGMSB', 'EGMSB/C1', 'EGMSB/C2', 'EGMSB/P', 'EGMSB/C1/P', 'EGMSB/C2/P',
    'EGGSB', 'EGGSB/C1', 'EGGSB/C2', 'EGGSB/P', 'EGGSB/C1/P', 'EGGSB/C2/P',
    'EDE', 'EDEBT', 'EDEBB', 'EDET', 'EDEB',
    'EDE/P', 'EDEBT/P', 'EDEBB/P', 'EDET/P', 'EDEB/P',
    'SSSC', 'SSSC/F', 'SSSC/P', 'SSSC/F/P',
    'SSSC/K4', 'SSSC/F/K4', 'SSSC/P/K4', 'SSSC/F/P/K4',
)  # fmt: skip


class UnfinishedTournament(ValueError):
    """A tournament that ran out of legal pairings before its last round."""


@dataclass
class TournamentSettings:
    """What a generated tournament is made of.

    Every field may be left unset, in which case a value is drawn for it
    (question 25); what is set is honoured exactly.
    """

    players: int | None = None
    rounds: int | None = None
    #: A team tournament's size, used in place of ``players`` when the
    #: event holds teams: the field is then the one the teams fill. Either
    #: of them asks for a team tournament; ``team_event`` asks for one
    #: without saying how big.
    team_event: bool = False
    teams: int | None = None
    players_per_team: int | None = None
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
    #: A team tournament's colour-preference rule (§1.7), which score is
    #: the primary one (§1.2.1), and whether the secondary score decides the
    #: colour allocation of §4.2.2. Together these are the TRF26 192 encoded
    #: type, and a run that leaves them unset draws each per tournament.
    team_colour_type: TeamColourType | None = None
    primary_score: ScoreType | None = None
    secondary_score_for_colours: bool | None = None
    #: The Baku acceleration method, which only an individual tournament
    #: can use.
    acceleration: bool | None = None
    #: The criteria the standings are ranked on, as TRF26 acronyms. Left
    #: out, the points and a few of the mandatory tie-breaks.
    tie_breaks: list[str] | None = None
    name: str = 'Generated tournament'
    #: Give the players and teams names to read rather than numbers, for a
    #: tournament somebody is going to look at.
    realistic_names: bool = False
    #: Pair the rounds and play them. Left out, the tournament is entered
    #: and nothing else: a field waiting for its first pairing.
    pair_rounds: bool = True

    def settled(
        self, chance: random.Random, team_event: bool = False
    ) -> 'TournamentSettings':
        """The same settings with a value drawn for everything unstated.

        In a team event the field is the teams and the players fill their
        boards, so the player count follows from the two rather than being
        drawn, and it is the teams that have to outnumber the rounds.
        """

        def frequency(stated: Frequency | None) -> Frequency:
            if stated is not None:
                return stated
            return Frequency(rate=chance.uniform(*_UNSTATED_RATE_RANGE))

        teams = players_per_team = None
        if team_event:
            teams = self.teams or chance.randint(*_UNSTATED_TEAM_RANGE)
            players_per_team = self.players_per_team or chance.randint(
                *_UNSTATED_TEAM_PLAYER_RANGE
            )
            players = teams * players_per_team
        else:
            players = self.players or chance.randint(*_UNSTATED_PLAYER_RANGE)
        rounds = self.rounds or chance.randint(*_UNSTATED_ROUND_RANGE)
        # More rounds than a field can fill would leave nobody left to meet.
        rounds = max(1, min(rounds, (teams or players) - 1))
        colour_type = self.team_colour_type
        primary_score = self.primary_score
        secondary_for_colours = self.secondary_score_for_colours
        if team_event:
            if colour_type is None:
                colour_type = chance.choice(list(TeamColourType))
            if primary_score is None:
                primary_score = chance.choice(list(ScoreType))
            if secondary_for_colours is None:
                secondary_for_colours = chance.choice((True, False))
        acceleration = self.acceleration
        if acceleration is None:
            acceleration = not team_event and chance.choice((True, False))
        tie_breaks = self.tie_breaks
        if tie_breaks is None:
            catalogue = (
                MANDATORY_TEAM_TIE_BREAKS
                if team_event
                else MANDATORY_INDIVIDUAL_TIE_BREAKS
            )
            tie_breaks = [
                'PTS',
                *chance.sample(
                    catalogue, chance.randint(*_UNSTATED_TIE_BREAK_COUNT_RANGE)
                ),
            ]
        return TournamentSettings(
            players=players,
            rounds=rounds,
            team_event=self.team_event,
            teams=teams,
            players_per_team=players_per_team,
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
            team_colour_type=colour_type,
            primary_score=primary_score,
            secondary_score_for_colours=secondary_for_colours,
            acceleration=acceleration,
            tie_breaks=list(tie_breaks),
            name=self.name,
            realistic_names=self.realistic_names,
            pair_rounds=self.pair_rounds,
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


class NameSource:
    """Names for the players and the teams, each one used once.

    A field of a hundred wants a hundred different people in it, and Faker
    repeats itself long before that, so a name already given is drawn
    again.
    """

    def __init__(self, faker: 'Faker') -> None:
        self.faker = faker
        self._taken: set[str] = set()

    def _fresh(self, make: 'Callable[[], str]') -> str:
        for _attempt in range(100):
            candidate = make()
            if candidate not in self._taken:
                self._taken.add(candidate)
                return candidate
        # A field larger than the names available -- there are fifty states
        # to name a club after -- is numbered apart rather than repeated.
        base = make()
        suffix = 2
        while f'{base} {suffix}' in self._taken:
            suffix += 1
        self._taken.add(f'{base} {suffix}')
        return f'{base} {suffix}'

    def player(self) -> tuple[str, str]:
        """A surname and a first name, in the order the records hold them."""
        full = self._fresh(
            lambda: f'{self.faker.last_name()} {self.faker.first_name()}'
        )
        last_name, _, first_name = full.partition(' ')
        return last_name, first_name

    def team(self) -> str:
        """A club named after a place, the way clubs are.

        The place is a real one: the invented cities Faker's own locale
        offers come out as Port Samanthaberg.
        """
        return self._fresh(
            lambda: f'{self.faker.administrative_unit()} Chess Club',
        )


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
        from data.pairings.variations import (
            StandardSwissVariation,
            StandardTeamSwissVariation,
        )

        # Read afresh: generating twice into one event has to see the first
        # tournament, and nothing here has touched the cached copy.
        EventLoader.unload_event(uniq_id)
        event = EventLoader().load_event(uniq_id)
        self._team_event = event.is_team_event
        settled = settings.settled(self.chance, team_event=self._team_event)
        # An event holds one tournament of a given name, and generating into
        # one that already holds a generated tournament is the ordinary case.
        name = event.get_unused_tournament_name(settled.name)
        assert settled.players is not None and settled.rounds is not None
        variation: PairingVariation
        if self._team_event:
            # The acceleration methods are Swiss variations of an individual
            # tournament, so a team event pairs the standard way whatever was
            # asked for.
            variation = StandardTeamSwissVariation()
        elif settled.acceleration:
            variation = BakuSwissVariation()
        else:
            variation = StandardSwissVariation()
        with EventDatabase(uniq_id, write=True) as database:
            tournament_id = database.add_stored_tournament(
                StoredTournament(
                    id=None,
                    name=name,
                    pairing=variation.id,
                    rounds=settled.rounds,
                    # The standard rating of each player, which is the
                    # rating the file states and the one the results are
                    # drawn from.
                    rating=TournamentRating.STANDARD.value,
                    player_rating_type=PlayerRatingType.FIDE.value,
                    team_player_count=settled.players_per_team,
                    team_colour_type=(
                        settled.team_colour_type.value
                        if settled.team_colour_type is not None
                        else None
                    ),
                    primary_score=(
                        settled.primary_score.value
                        if settled.primary_score is not None
                        else None
                    ),
                    secondary_score_for_colours=(
                        True
                        if settled.secondary_score_for_colours is None
                        else settled.secondary_score_for_colours
                    ),
                )
            )
            if self._team_event:
                self._add_teams(database, tournament_id, settled)
            else:
                self._add_players(database, tournament_id, settled)

        event = EventLoader().load_event(uniq_id)
        assert settled.tie_breaks is not None
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

        if not settled.pair_rounds:
            return tournament_id

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
            if error := self._play_round(uniq_id, tournament_id, round_, settled):
                # A field can run out of legal pairings before the rounds run
                # out — a nearly round-robin Swiss where everyone has met
                # everyone they are allowed to. A generated tournament is
                # a finished one, so it is refused rather than cut short.
                EventLoader.unload_event(uniq_id)
                with EventDatabase(uniq_id, write=True) as database:
                    database.delete_stored_tournament(tournament_id)
                if round_ == 1:
                    raise ValueError(f'round 1: {error}')
                raise UnfinishedTournament(
                    _(
                        'Round {round} of {rounds} could not be paired ({error}):'
                        ' the tournament was not generated.'
                    ).format(round=round_, rounds=settled.rounds, error=error)
                )
        return tournament_id

    def _names(self, settled: TournamentSettings) -> 'NameSource | None':
        """Where the players and teams get their names, or None to number
        them.

        Faker is a development dependency: a build has none, and a
        tournament generated there is numbered rather than the generation
        failing.
        """
        if not settled.realistic_names:
            return None
        try:
            from faker import Faker
        except ImportError:
            logger.info('Faker is not installed: the players are numbered.')
            return None
        faker = Faker()
        # Seeded from the generator's own seed, so a tournament asked for
        # twice is named the same twice (question 30).
        faker.seed_instance(self.seed)
        return NameSource(faker)

    def _stored_player(
        self,
        rating: int,
        last_name: str,
        first_name: str,
        team_id: int | None = None,
        team_index: int | None = None,
    ) -> StoredPlayer:
        return StoredPlayer(
            id=None,
            last_name=last_name,
            first_name=first_name,
            ratings={
                TournamentRating.STANDARD.value: PlayerRating(fide=rating).stored_value,
            },
            check_in=True,
            team_id=team_id,
            team_index=team_index,
        )

    def _add_players(
        self,
        database: EventDatabase,
        tournament_id: int,
        settled: TournamentSettings,
    ) -> None:
        names = self._names(settled)
        for number, rating in enumerate(settled.player_ratings(self.chance), start=1):
            last_name, first_name = (
                names.player() if names else (f'Player{number:04d}', 'Test')
            )
            player_id = database.add_stored_player(
                self._stored_player(rating, last_name, first_name)
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    tournament_id=tournament_id,
                    player_id=player_id,
                    pairing_number=number,
                )
            )

    def _add_teams(
        self,
        database: EventDatabase,
        tournament_id: int,
        settled: TournamentSettings,
    ) -> None:
        """The teams and the players filling their boards.

        The ratings run down the field as they do for an individual
        tournament, so the first team is the strongest and, within a team,
        board one is: a seeding a real team event would recognise.
        """
        assert settled.teams is not None and settled.players_per_team is not None
        names = self._names(settled)
        ratings = settled.player_ratings(self.chance)
        boards = settled.players_per_team
        for number in range(1, settled.teams + 1):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=names.team() if names else f'Team{number:03d}',
                    tournament_id=tournament_id,
                    pairing_number=number,
                    check_in=True,
                )
            )
            for board in range(boards):
                rating = ratings[(number - 1) * boards + board]
                last_name, first_name = (
                    names.player()
                    if names
                    else (f'Team{number:03d}Board{board + 1}', 'Test')
                )
                player_id = database.add_stored_player(
                    self._stored_player(
                        rating,
                        last_name,
                        first_name,
                        team_id=team_id,
                        team_index=board,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=board,
                    )
                )

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
    ) -> str:
        """Pair the round and give every board a result, or say why the
        round could not be paired."""
        tournament = self._tournament(uniq_id, tournament_id)
        # A team bye is written down as a match with no opponent, which makes
        # the round a paired one: what is left is the rest of the field, so
        # the engine is asked to finish the round rather than to start it.
        rest_of_round = False
        if self._team_event:
            rest_of_round = self._give_team_byes(uniq_id, tournament, round_, settings)
        else:
            self._give_byes(tournament, round_, settings)
        tournament = self._tournament(uniq_id, tournament_id)
        error = tournament.generate_round_pairings(
            round_, partial_pairings=rest_of_round
        )
        if (
            not error
            and rest_of_round
            and not self._round_is_paired(tournament, round_)
        ):
            # Teams rested at random can leave a field with no legal pairing
            # at all -- every remaining pair has already met, say. Asked to
            # finish a round, the engine answers that with nothing rather
            # than with an error, so the byes are taken back and the whole
            # field paired instead of the round being left empty.
            self._clear_team_byes(uniq_id, tournament, round_)
            tournament = self._tournament(uniq_id, tournament_id)
            error = tournament.generate_round_pairings(round_)
        if error:
            return error
        tournament = self._tournament(uniq_id, tournament_id)
        self._enter_results(tournament, round_, settings)
        return ''

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

    @staticmethod
    def _round_is_paired(tournament: 'Tournament', round_: int) -> bool:
        """Whether the round holds a match, as against nothing but byes."""
        return any(
            team_board.stored_team_board.team_b_id is not None
            for team_board in tournament.get_round_team_boards(round_)
        )

    @staticmethod
    def _clear_team_byes(uniq_id: str, tournament: 'Tournament', round_: int) -> None:
        """Take back every bye given for the round, leaving the whole field
        to be paired."""
        manual = {bye_type.value for bye_type in TeamByeType.manual_bye_types()}
        rested = [
            team_board.stored_team_board.team_a_id
            for team_board in tournament.get_round_team_boards(round_)
            if team_board.stored_team_board.bye_type in manual
        ]
        with EventDatabase(uniq_id, write=True) as database:
            for team_id in rested:
                if (team := tournament.teams_by_id.get(team_id)) is not None:
                    team.set_round_bye(round_, None, database)

    def _give_team_byes(
        self,
        uniq_id: str,
        tournament: 'Tournament',
        round_: int,
        settings: TournamentSettings,
    ) -> bool:
        """Each team's chance of sitting this round out, and whether any did.

        A team event's byes are the team's: the whole team misses the round
        and its boards are never paired, where an individual bye takes one
        player out of the field.
        """
        kinds = (
            ('full_point_byes', TeamByeType.FPB),
            ('half_point_byes', TeamByeType.HPB),
            ('zero_point_byes', TeamByeType.ZPB),
        )
        free = list(tournament.teams)
        self.chance.shuffle(free)
        # The more of the field rests, the less room the rest have to meet
        # somebody they have not met: most of it plays, whatever was asked
        # for, and a round the byes strand is paired again without them.
        allowed = max(0, len(free) - max(2, (len(free) + 1) // 2))
        resting = False
        with EventDatabase(uniq_id, write=True) as database:
            for name, bye_type in kinds:
                frequency = getattr(settings, name)
                planned = self._this_round(name, round_)
                taking = (
                    planned
                    if planned is not None
                    else frequency.occurrences(len(free), self.chance)
                )
                taking = min(taking, allowed)
                allowed -= taking
                for team in free[:taking]:
                    team.set_round_bye(round_, bye_type.value, database)
                    resting = True
                free = free[taking:]
        return resting

    def _enter_results(
        self, tournament: 'Tournament', round_: int, settings: TournamentSettings
    ) -> None:
        """One result per board, drawn from the two ratings."""
        played = [
            board
            for board in tournament.get_round_boards(round_)
            # A player left over by an odd field already holds the bye the
            # pairing system gives them, and a team match may hold a board
            # one side leaves empty: neither is a game to give a result to.
            if board.optional_white_tournament_player is not None
            and board.black_tournament_player is not None
        ]
        # A team match numbers its own boards, so a board is known by its
        # place in the round rather than by its id.
        order = list(range(len(played)))
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
            for index in order[:taking]:
                decided[index] = (
                    result
                    if result is not None
                    else self.chance.choice(UNUSUAL_RESULTS)
                )
            order = order[taking:]
        for index, board in enumerate(played):
            white = board.optional_white_tournament_player
            black = board.black_tournament_player
            assert white is not None and black is not None, (
                'boards missing a player were left out'
            )
            tournament.add_result(
                board,
                decided.get(index)
                or draw_result(
                    white.rating or DEFAULT_RATING,
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
        if settings.team_event or settings.teams or settings.players_per_team:
            with EventDatabase(uniq_id, write=True) as database:
                stored_event = database.load_stored_event()
                stored_event.event_type = EventType.TEAM
                database.update_stored_event(stored_event)
            EventLoader.unload_event(uniq_id)
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
