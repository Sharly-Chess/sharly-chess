"""Reading TRF06 and TRF16 files as TRF26.

The two older versions carry only the 001 player records and the 012-132
tournament records; TRF06 moreover has no bye or unrated-game codes. What
the file leaves out is filled in here, and every such decision is listed in
``adjustments`` so that the user can be told before the import. Fields of
any version that programs fill with something else than the format defines
are repaired the same way, rather than the file being refused.
"""

import re
from collections import defaultdict
from datetime import date
from enum import StrEnum

from common.i18n import _, ngettext
from common.sharly_chess_config import SharlyChessConfig
from .trf_data import TrfGame, TrfTournament
from .trf_mappers import TrfPlayerTitle
from .trf_utils import parse_trf_date, parse_trf_year


class TrfVersion(StrEnum):
    TRF06 = 'TRF06'
    TRF16 = 'TRF16'
    TRF26 = 'TRF26'


class TrfLegacyAdapter:
    #: TRF16 result codes TRF06 does not have.
    TRF16_RESULTS = frozenset('WDLHFUZ')
    #: Record 092 wordings of a round robin, lower-cased.
    ROUND_ROBIN_WORDS = (
        'robin',
        'berger',
        'rundenturnier',
        'toutes rondes',
        'todos contra todos',
        'all-play-all',
        'all play all',
    )
    DOUBLE_WORDS = ('double', 'doppel', 'doble')

    def __init__(self, trf_tournament: TrfTournament):
        self.trf_tournament = trf_tournament
        self.version = self._detect_version()
        self.adjustments: list[str] = []

    def _detect_version(self) -> TrfVersion:
        trf = self.trf_tournament
        if any(
            (
                trf.num_rounds,
                trf.initial_color,
                trf.individuals_point_system,
                trf.teams_point_system,
                trf.starting_rank_method,
                trf.pairing_controller_id,
                trf.encoded_type,
                trf.tie_breaks,
                trf.standings_tie_breaks,
                trf.time_control,
                trf.board_color_sequence,
                trf.teams,
                trf.round_byes,
                trf.accelerated_rounds,
                trf.prohibited_pairings,
                trf.team_pabs,
                trf.team_forfeited_matches,
                trf.oodo_team_pairings,
                trf.abnormal_points_assignments,
                trf.informative_team_pairings_records,
                trf.informative_team_results_records,
                trf.national_players_by_federation,
            )
        ):
            return TrfVersion.TRF26
        if trf.xx_fields or any(
            game.result.upper() in self.TRF16_RESULTS
            for player in trf.players
            for game in player.games
        ):
            return TrfVersion.TRF16
        return TrfVersion.TRF06

    def adapt(self) -> None:
        """Rewrite the parsed file as the TRF26 file it stands for."""
        self._report_joined_lines()
        self._adapt_partial_birth_dates()
        self._repair_player_fields()
        self._unpair_empty_games_against_missing_players()
        if self.version == TrfVersion.TRF26:
            return
        if self.version == TrfVersion.TRF16:
            self._adapt_byes('1=0')
        else:
            self._adapt_byes('+1=0-')
            self._adapt_trf06_forfeit_colours()
            self.adjustments.append(
                _(
                    'All games count for rating: TRF06 cannot mark a game that '
                    'should not (less than one move played).'
                )
            )
        self._adapt_day_first_round_dates()
        self._drop_unpaired_round_blanks()
        self._read_xxz()
        self._set_pairing_system()
        self._set_num_rounds()
        self._check_points()
        self.adjustments.append(
            _('No tie-breaks: the file does not list them. Set them after the import.')
        )
        self.adjustments.append(
            _('No time control: record 122 gives it as text only ({text}).').format(
                text=self.trf_tournament.allotted_time
            )
            if self.trf_tournament.allotted_time
            else _('No time control: the file does not give it.')
        )
        unsplit_names = sum(
            1 for player in self.trf_tournament.players if ',' not in player.name
        )
        if unsplit_names:
            self.adjustments.append(
                ngettext(
                    '{count} name has no comma between last and first name: '
                    'it is imported whole as the last name.',
                    '{count} names have no comma between last and first name: '
                    'they are imported whole as the last name.',
                    unsplit_names,
                ).format(count=unsplit_names)
            )

    def _games_by_round(self) -> dict[int, list[tuple[int, TrfGame]]]:
        games_by_round: dict[int, list[tuple[int, TrfGame]]] = defaultdict(list)
        for player in self.trf_tournament.players:
            for game in player.games:
                games_by_round[game.round].append((player.id, game))
        return games_by_round

    @staticmethod
    def _format_rounds(rounds: set[int]) -> str:
        return ngettext('round {rounds}', 'rounds {rounds}', len(rounds)).format(
            rounds=', '.join(str(round_) for round_ in sorted(rounds))
        )

    def _adapt_byes(self, codes: str) -> None:
        """TRF06 writes every bye as opponent ``0000`` followed by the
        points it gave, and programs kept doing so for ``1`` / ``=`` /
        ``0`` in TRF16 files, where those codes need an opponent. A won
        bye is the pairing-allocated bye when it is the only one of its
        round, a full-point bye otherwise."""
        pab_rounds: set[int] = set()
        fpb_rounds: set[int] = set()
        hpb_rounds: set[int] = set()
        zpb_rounds: set[int] = set()
        won_codes = ''.join(code for code in '+1' if code in codes)
        for round_, games in self._games_by_round().items():
            byes = [
                game
                for __, game in games
                if not game.opponent_id and game.result in codes
            ]
            won = sum(
                1
                for __, game in games
                if not game.opponent_id
                and (game.result in won_codes or game.result.upper() == 'U')
            )
            for game in byes:
                if game.result in won_codes:
                    if won == 1:
                        game.result = 'U'
                        pab_rounds.add(round_)
                    else:
                        game.result = 'F'
                        fpb_rounds.add(round_)
                elif game.result == '=':
                    game.result = 'H'
                    hpb_rounds.add(round_)
                elif game.result in '0-':
                    game.result = 'Z'
                    zpb_rounds.add(round_)
                else:
                    continue
                game.color = '-'
        for rounds, message in (
            (pab_rounds, _('Won byes read as pairing-allocated byes ({rounds}).')),
            (
                fpb_rounds,
                _(
                    'Won byes read as full-point byes, the round having more '
                    'than one ({rounds}).'
                ),
            ),
            (hpb_rounds, _('Drawn byes read as half-point byes ({rounds}).')),
            (
                zpb_rounds,
                _('Lost byes read as zero-point byes ({rounds}).'),
            ),
        ):
            if rounds:
                self.adjustments.append(
                    message.format(rounds=self._format_rounds(rounds))
                )

    def _adapt_trf06_forfeit_colours(self) -> None:
        """TRF06 allows ``-`` (no colour) against a named opponent, which
        it uses for forfeits. The colour is taken from the opponent's
        block, or white is given to the lower starting rank."""
        games_by_round = self._games_by_round()
        adapted: set[int] = set()
        for round_, games in games_by_round.items():
            game_by_player = dict(games)
            for player_id, game in games:
                if not game.opponent_id or game.color in 'wbWB':
                    continue
                opponent_game = game_by_player.get(game.opponent_id)
                opponent_color = opponent_game.color.lower() if opponent_game else ''
                if opponent_color in ('w', 'b'):
                    game.color = 'b' if opponent_color == 'w' else 'w'
                else:
                    game.color = 'w' if player_id < game.opponent_id else 'b'
                adapted.add(round_)
        if adapted:
            self.adjustments.append(
                _(
                    'Colours given to games the file pairs without a colour ({rounds}).'
                ).format(rounds=self._format_rounds(adapted))
            )

    def _report_joined_lines(self) -> None:
        player_ids = sorted(set(self.trf_tournament.joined_player_lines))
        if player_ids:
            self.adjustments.append(
                _(
                    'Player lines split over several lines joined back '
                    '(players {players}).'
                ).format(players=self._format_ids(player_ids))
            )

    @staticmethod
    def _format_ids(ids: list[int]) -> str:
        return ', '.join(str(id_) for id_ in ids[:10]) + (
            ', …' if len(ids) > 10 else ''
        )

    def _repair_player_fields(self) -> None:
        """Sex, title, federation and birth date only raise a warning when
        wrong, the points are recomputed, and a number that is not a FIDE
        number identifies no one: what cannot be read is left empty."""
        federations = SharlyChessConfig().federations
        ids_by_field: dict[str, list[int]] = defaultdict(list)
        values_by_field: dict[str, set[str]] = defaultdict(set)
        for player in self.trf_tournament.players:
            for field, value in player.unreadable.items():
                ids_by_field[field].append(player.id)
                values_by_field[field].add(value)
            player.unreadable = {}
            try:
                TrfPlayerTitle.get_core_object(player.title)
            except KeyError:
                ids_by_field['title'].append(player.id)
                values_by_field['title'].add(player.title)
                player.title = ''
            if player.federation and player.federation.upper() not in federations:
                ids_by_field['federation'].append(player.id)
                values_by_field['federation'].add(player.federation)
                player.federation = ''
            if player.birth_date and not (
                parse_trf_date(player.birth_date) or parse_trf_year(player.birth_date)
            ):
                ids_by_field['birth_date'].append(player.id)
                values_by_field['birth_date'].add(player.birth_date)
                player.birth_date = ''
        messages = {
            'title': _('Titles not recognised ({values}), left empty'),
            'federation': _('Federations not recognised ({values}), left empty'),
            'birth_date': _('Birth dates not readable ({values}), left empty'),
            'fide_id': _('Not FIDE numbers ({values}), left empty'),
            'points': _(
                'Points written with another decimal separator ({values}), '
                'read with a point'
            ),
        }
        for field, message in messages.items():
            if field not in ids_by_field:
                continue
            values = sorted(values_by_field[field])
            self.adjustments.append(
                _('{message}: players {players}.').format(
                    message=message.format(
                        values=', '.join(values[:5])
                        + (', …' if len(values) > 5 else '')
                    ),
                    players=self._format_ids(ids_by_field[field]),
                )
            )

    def _unpair_empty_games_against_missing_players(self) -> None:
        """A game with no result against a player the file does not list
        says nothing but that a pairing was once made: the player is read
        as not paired. With a result, the file stays refused."""
        player_ids = {player.id for player in self.trf_tournament.players}
        unpaired: list[str] = []
        for player in self.trf_tournament.players:
            for game in player.games:
                if (
                    game.opponent_id
                    and game.opponent_id not in player_ids
                    and game.result == ' '
                ):
                    unpaired.append(
                        _('player {player}, round {round}').format(
                            player=player.id, round=game.round
                        )
                    )
                    game.opponent_id = None
                    game.color = '-'
        if unpaired:
            self.adjustments.append(
                _(
                    'Games without a result against players missing from the '
                    'file read as not paired ({games}).'
                ).format(games='; '.join(unpaired))
            )

    def _adapt_partial_birth_dates(self) -> None:
        """Programs fill an unknown day and month with the separators
        alone (``1975.  .``, ``/  /``): the year is kept when there is
        one."""
        adapted = 0
        for player in self.trf_tournament.players:
            match = re.fullmatch(r'(\d{4})?[\s./-]+', player.birth_date)
            if match is None:
                continue
            player.birth_date = match.group(1) or ''
            adapted += 1
        if adapted:
            self.adjustments.append(
                ngettext(
                    '{count} birth date has no day or month: only its year, if '
                    'any, is imported.',
                    '{count} birth dates have no day or month: only their year, '
                    'if any, is imported.',
                    adapted,
                ).format(count=adapted)
            )

    def _drop_unpaired_round_blanks(self) -> None:
        """A round in which nobody has an opponent or the pairing-allocated
        bye has not been paired: its blank blocks are players still to be
        paired, not zero-point byes. The byes already entered are kept."""
        dropped: set[int] = set()
        for round_, games in self._games_by_round().items():
            if any(
                game.opponent_id or game.result.upper() == 'U' for __, game in games
            ):
                continue
            if any(game.result == ' ' for __, game in games):
                dropped.add(round_)
        if not dropped:
            return
        for player in self.trf_tournament.players:
            player.games = [
                game
                for game in player.games
                if not (game.round in dropped and game.result == ' ')
            ]
        self.adjustments.append(
            _(
                'Not paired yet ({rounds}): blank entries are read as players '
                'still to be paired, not as zero-point byes.'
            ).format(rounds=self._format_rounds(dropped))
        )

    def _read_xxz(self) -> None:
        """``XXZ`` lists the players absent from the next round."""
        value = self.trf_tournament.xx_fields.pop('XXZ', '')
        ids = {int(token) for token in value.split() if token.isdigit()}
        if not ids:
            return
        next_round = 1 + max(
            (
                game.round
                for player in self.trf_tournament.players
                for game in player.games
            ),
            default=0,
        )
        for player in self.trf_tournament.players:
            if player.id in ids:
                player.games.append(TrfGame(None, '-', 'Z', next_round))
        self.adjustments.append(
            _('XXZ: players {players} absent from round {round}.').format(
                players=', '.join(str(id_) for id_ in sorted(ids)),
                round=next_round,
            )
        )

    def _round_robin_cycles(self) -> int:
        """1 or 2 when the 092 text or the pairings show a single or
        double round robin, 0 otherwise."""
        text = self.trf_tournament.type.lower()
        if any(word in text for word in self.ROUND_ROBIN_WORDS):
            return 2 if any(word in text for word in self.DOUBLE_WORDS) else 1
        players = self.trf_tournament.players
        if len(players) < 3:
            return 0
        meetings: dict[frozenset[int], int] = defaultdict(int)
        for player in players:
            for game in player.games:
                if game.opponent_id:
                    meetings[frozenset((player.id, game.opponent_id))] += 1
        pairs = len(players) * (len(players) - 1) // 2
        counts = {count // 2 for count in meetings.values()}
        if len(meetings) == pairs and counts in ({1}, {2}):
            return counts.pop()
        return 0

    def _set_pairing_system(self) -> None:
        cycles = self._round_robin_cycles()
        trf = self.trf_tournament
        if cycles:
            trf.encoded_type = (
                'FIDE_DOUBLEROUNDROBIN' if cycles == 2 else 'FIDE_ROUNDROBIN'
            )
            message = (
                _('Pairing system set to double round robin: {reason}.')
                if cycles == 2
                else _('Pairing system set to round robin: {reason}.')
            )
        else:
            trf.encoded_type = 'FIDE_DUTCH_2026'
            message = _('Pairing system set to FIDE Dutch: {reason}.')
        reason = (
            _('the file does not code it, and describes the tournament as "{type}"')
            if trf.type
            else _('the file does not code it')
        ).format(type=trf.type)
        self.adjustments.append(message.format(reason=reason))

    def _adapt_day_first_round_dates(self) -> None:
        """Some programs write the 132 dates year, day, month
        (``11.25.02``). A date that reads only that way, and then falls
        between the start and end of the tournament, is taken so."""
        trf = self.trf_tournament
        start = parse_trf_date(trf.start_date)
        end = parse_trf_date(trf.end_date)
        if start is None or end is None:
            return
        adapted: set[int] = set()
        for index, value in enumerate(trf.round_dates):
            if parse_trf_date(value):
                continue
            match = re.fullmatch(r'(\d\d)([./-])(\d\d)\2(\d\d)', value)
            if match is None:
                continue
            try:
                swapped = date(
                    2000 + int(match.group(1)),
                    int(match.group(4)),
                    int(match.group(3)),
                )
            except ValueError:
                continue
            if start <= swapped <= end:
                trf.round_dates[index] = swapped.strftime('%y/%m/%d')
                adapted.add(index + 1)
        if adapted:
            self.adjustments.append(
                _(
                    'Round dates written year, day, month read as such, the '
                    'only reading within the tournament dates ({rounds}).'
                ).format(rounds=self._format_rounds(adapted))
            )

    def _set_num_rounds(self) -> None:
        trf = self.trf_tournament
        xxr = trf.xx_fields.pop('XXR', '').strip()
        if trf.num_rounds:
            return
        if xxr.isdigit():
            trf.num_rounds = int(xxr)
            self.adjustments.append(
                _('Number of rounds ({rounds}) read from XXR.').format(
                    rounds=trf.num_rounds
                )
            )
            return
        if trf.encoded_type in ('FIDE_ROUNDROBIN', 'FIDE_DOUBLEROUNDROBIN'):
            players = len(trf.players)
            trf.num_rounds = (players - 1 if players % 2 == 0 else players) * (
                2 if trf.encoded_type == 'FIDE_DOUBLEROUNDROBIN' else 1
            )
            message = _(
                'Number of rounds set to {rounds}, the length of the round '
                'robin: the file does not give it.'
            )
        else:
            trf.num_rounds = trf.num_rounds_estimation
            message = _(
                'Number of rounds set to {rounds}, from the rounds in the file: '
                'the file does not give it.'
            )
        self.adjustments.append(message.format(rounds=trf.num_rounds))

    def _check_points(self) -> None:
        """No scoring record: the defaults are used, 1 / ½ / 0 with the
        pairing-allocated bye worth a win. The points column of the file
        shows whether they are the ones it was scored with."""
        points_by_result = {'1': 1.0, '+': 1.0, 'W': 1.0, 'U': 1.0, 'F': 1.0}
        points_by_result |= {'=': 0.5, 'D': 0.5, 'H': 0.5}
        mismatches = [
            player.id
            for player in self.trf_tournament.players
            if abs(
                sum(
                    points_by_result.get(game.result.upper(), 0.0)
                    for game in player.games
                )
                - player.points
            )
            > 0.01
        ]
        self.adjustments.append(
            _(
                'Scoring set to 1 / ½ / 0, the pairing-allocated bye worth a '
                'win: the file does not give it.'
            )
        )
        if mismatches:
            self.adjustments.append(
                ngettext(
                    'The points the file gives player {players} do not match '
                    'this scoring.',
                    'The points the file gives {count} players do not match '
                    'this scoring (players {players}).',
                    len(mismatches),
                ).format(
                    count=len(mismatches),
                    players=', '.join(str(id_) for id_ in mismatches[:10])
                    + (', …' if len(mismatches) > 10 else ''),
                )
            )
