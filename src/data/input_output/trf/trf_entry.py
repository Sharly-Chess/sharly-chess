from abc import ABC, abstractmethod
from typing import Any

from common.exception import ImporterError
from common.i18n import _
from .trf_data import (
    TrfAcceleratedRound,
    TrfDeprecatedTeam,
    TrfGame,
    TrfNationalPlayer,
    TrfPlayer,
    TrfProhibitedPairing,
    TrfTeam,
    TrfTournament,
    TrfRoundBye,
    TrfTeamPABs,
    TrfTeamForfeitedMatch,
    TrfOOdOTeamPairing,
    TrfAbnormalPointsAssignment,
)
import re

from .trf_utils import (
    float_display,
    int_or_default,
    float_or_default,
    split_ints,
    split_optional_ints,
)


class TrfEntry(ABC):
    def __init__(self, din: str):
        self.din = din

    @abstractmethod
    def dump(self, fp, tournament: TrfTournament):
        pass

    @abstractmethod
    def load(self, tournament: TrfTournament, data: str):
        pass

    def get_header(self, tournament: TrfTournament) -> str | None:
        """Header displayed before dumping all the lines of the table."""
        return None

    def line_exception(self, data: str) -> ImporterError:
        return ImporterError(
            _('Line not recognized: {line}').format(line=f'{self.din} {data}')
        )


class SingleLineEntry(TrfEntry):
    def __init__(self, din: str, field_name: str):
        super().__init__(din)
        self.field_name = field_name

    def dump(self, fp, tournament: TrfTournament):
        value = tournament.__dict__[self.field_name]
        if not value:
            return
        header = self.get_header(tournament)
        if header:
            fp.write(f'\n### {header}\n')
        fp.write(f'{self.din} {self.format(value)}\n')

    def format(self, value: Any) -> str:
        return str(value)

    def load(self, tournament: TrfTournament, data: str):
        value = self.parse(data)
        tournament.__dict__[self.field_name] = value

    def parse(self, data: str) -> Any:
        return data.strip()


class MultipleLinesEntry(TrfEntry):
    def __init__(self, din, field_name):
        super().__init__(din)
        self.field_name = field_name

    def dump(self, fp, tournament: TrfTournament):
        value = tournament.__dict__[self.field_name]
        if not value:
            return
        header = self.get_header(tournament)
        if header:
            fp.write(f'\n### {header}\n')
        for item in value:
            fp.write(f'{self.din} {self.format(item)}\n')

    def format(self, value: Any) -> str:
        return str(value)

    def load(self, tournament: TrfTournament, data: str):
        value = self.parse(data)
        tournament.__dict__[self.field_name].append(value)

    def parse(self, data: str) -> Any:
        return data.strip()


class SingleLineIntEntry(SingleLineEntry):
    def parse(self, data: str) -> Any:
        return int(data.strip())


class SingleLineListEntry(SingleLineEntry):
    def __init__(self, din, field_name, separator=','):
        super().__init__(din, field_name)
        self.separator = separator

    def format(self, value: Any) -> str:
        return self.separator.join(value)

    def parse(self, data: str) -> Any:
        return [s.strip() for s in data.strip().split(self.separator) if s.strip()]


class RoundDatesEntry(SingleLineEntry):
    def __init__(self):
        super().__init__('132', 'round_dates')

    def get_header(self, tournament: TrfTournament) -> str | None:
        if not [date_ for date_ in tournament.round_dates if date_]:
            return None
        header = ' ' * 86
        num_columns = len(tournament.round_dates)
        for column in range(1, num_columns + 1):
            header += f'  {str(column).rjust(8, "R")}'
        return header

    def format(self, value: Any) -> str:
        return ' ' * 88 + '  '.join(date_.rjust(8) for date_ in value)

    def parse(self, data: str) -> Any:
        return [s for s in data.strip().split(' ') if s]


class PointSystemEntry(SingleLineEntry):
    def format(self, value: Any) -> str:
        return '   '.join(
            f'{symbol:>2}{float_display(score, 4)}' for symbol, score in value.items()
        )

    def parse(self, data: str) -> Any:
        point_system: dict[str, float] = {}
        while len(data) >= 3:
            entry = data[:9]
            point_system[entry[:2].strip()] = float(entry[2:].strip())
            data = data[9:]
        return point_system


class PlayerEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<id>[ \d]{4}) (?P<gender>[\w ])(?P<title>[\w ]{3}) '
        r'(?P<name>.{33}) (?P<rating>[ \d]{4}) (?P<federation>[\w ]{3}) '
        r'(?P<fide_id>[ \d]{11}) (?P<birth_date>.{10}) (?P<points>[ \d.]{4}) '
        r'(?P<rank>[ \d]{4})(?P<games>(\s\s[ \d]{4} [bsw\- ] [1=0+wdl\-hfuz ]| {10})*)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('001', 'players')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'SSSS sTTT NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN RRRR FFF IIIIIIIIIII BBBB/BB/BB PPPP RRRR'
        num_columns = max(len(player.games) for player in tournament.players)
        for column in range(1, num_columns + 1):
            col = str(column % 10)
            header += f'  {col * 4} {col} {col}'
        return header

    def format(self, value: Any) -> str:
        player: TrfPlayer = value
        line = (
            f'{player.id:>4}'
            f' {player.gender:1}'
            f'{player.title:>3}'
            f' {player.name[:33]:<33}'
            f' {player.rating or "":>4}'
            f' {player.federation:<3}'
            f' {player.fide_id or "":>11}'
            f' {player.birth_date:>10}'
            f' {float_display(player.points, 4)}'
            f' {"" if player.rank is None else player.rank:>4}'
        )
        for game in player.games:
            sr = '0000' if game.opponent_id == 0 else game.opponent_id or ''
            line += f'  {sr:>4} {game.color:1} {game.result:1}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)

        return TrfPlayer(
            id=int(match.group('id')),
            gender=match.group('gender'),
            title=match.group('title').strip(),
            name=match.group('name').strip(),
            rating=int_or_default(match.group('rating'), 0),
            federation=match.group('federation').strip(),
            fide_id=int_or_default(match.group('fide_id')),
            birth_date=match.group('birth_date').strip(),
            points=float(match.group('points')),
            rank=int_or_default(match.group('rank')),
            games=self.parse_games(match.group('games')[2:].rstrip()),
        )

    def parse_games(self, string) -> list[TrfGame]:
        round_ = 1
        games: list[TrfGame] = []
        while len(string) >= 8:
            games.append(
                TrfGame(
                    opponent_id=int_or_default(string[:4].strip()),
                    color=string[5],
                    result=string[7],
                    round=round_,
                )
            )
            round_ += 1
            string = string[10:]
        return games


class NationalPlayerEntry(TrfEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<player_id>[ \d]{4}) (?P<gender>[\w ])(?P<classification>[\w ]{3}) '
        r'(?P<name>.{33}) (?P<rating>[ \d]{4}) (?P<origin>[\w ]{3}) '
        r'(?P<national_id>.{11}) (?P<birth_date>.{10})\s*$',
        re.IGNORECASE,
    )

    def dump(self, fp, tournament: TrfTournament):
        players = tournament.national_players_by_federation.get(self.din, [])
        if not players:
            return
        fp.write(
            '\n### SSSS sCCC NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN RRRR OOO IIIIIIIIIII BBBB/BB/BB\n'
        )
        for player in players:
            fp.write(f'{self.din} {self.format(player)}\n')

    def format(self, player: TrfNationalPlayer) -> str:
        return (
            f'{player.player_id:>4}'
            f' {player.gender:1}'
            f'{player.classification:>3}'
            f' {player.name[:33]:<33}'
            f' {player.rating or "":>4}'
            f' {player.origin:<3}'
            f' {player.national_id:>11}'
            f' {player.birth_date:>10}'
        )

    def load(self, tournament: TrfTournament, data: str):
        match = self.LINE_PATTERN.fullmatch(data.ljust(80))
        if match is None:
            raise self.line_exception(data)

        player_id = int(match.group('player_id'))
        player = next(
            (player for player in tournament.players if player.id == player_id),
            None,
        )
        if not player:
            raise ImporterError(
                _('National rating support for unknown player [{player}].').format(
                    player=player_id,
                )
            )
        player.national_player_by_federation[self.din] = TrfNationalPlayer(
            player_id=player_id,
            gender=match.group('gender'),
            classification=match.group('classification').strip(),
            name=match.group('name').strip(),
            rating=int_or_default(match.group('rating'), 0),
            origin=match.group('origin').strip(),
            national_id=match.group('national_id').strip(),
            birth_date=match.group('birth_date').strip(),
        )


class DeprecatedTeamEntry(MultipleLinesEntry):
    def __init__(self):
        super().__init__('013', 'deprecated_teams')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN'
        num_columns = max(len(team.player_ids) for team in tournament.deprecated_teams)
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        team: TrfDeprecatedTeam = value
        player_ids = ' '.join(f'{s:>4}' for s in team.player_ids)
        return f'{team.name[:32]:32} {player_ids}'

    def parse(self, data: str) -> Any:
        return TrfDeprecatedTeam(name=data[:32], player_ids=split_ints(data[32:], 5))


class TeamEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<id>[ \d]{3}) (?P<name>.{32}) (?P<nickname>[ \w]{5}) '
        r'(?P<strength_factor>[ \d]{6}) (?P<match_points>[ \d.]{6}) '
        r'(?P<game_points>[ \d.]{6}) (?P<rank>[ \d]{3}) (?P<player_ids>( [ \d]{4})*)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('310', 'teams')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'SSS NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN FFFFF EEEEEE MMMMMM GGGGGG RRR '
        num_columns = max(len(team.player_ids) for team in tournament.teams)
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        team: TrfTeam = value
        line = (
            f'{team.id:>3}'
            f' {team.name[:32]:<32}'
            f' {team.nickname[:5]:<5}'
            f' {team.strength_factor:>6}'
            f' {float_display(team.match_points, 6)}'
            f' {float_display(team.game_points, 6)}'
            f' {team.rank:>3} '
        )
        for player_id in team.player_ids:
            line += f' {player_id:>4}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfTeam(
            id=int(match.group('id')),
            name=match.group('name').strip(),
            nickname=match.group('nickname').strip(),
            strength_factor=int_or_default(match.group('strength_factor'), 0),
            match_points=float(match.group('match_points')),
            game_points=float(match.group('game_points')),
            rank=int_or_default(match.group('rank')),
            player_ids=split_ints(match.group('player_ids'), 5),
        )


class AcceleratedRoundEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<match_points>[ \d.]{4}) (?P<game_points>[ \d.]{4}) '
        r'(?P<first_round>[ \d]{3}) (?P<last_round>[ \d]{3}) '
        r'(?P<first_id>[ \d]{4}) (?P<last_id>[ \d]{4})\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('250', 'accelerated_rounds')

    def get_header(self, tournament: TrfTournament) -> str | None:
        return 'MMMM GGGG RRF RRL PPPF PPPL'

    def format(self, value: Any) -> str:
        round_: TrfAcceleratedRound = value
        return (
            f'{float_display(round_.match_points, 4)}'
            f' {float_display(round_.game_points, 4)}'
            f' {round_.first_round:>3}'
            f' {round_.last_round:>3}'
            f' {round_.first_id:>4}'
            f' {round_.last_id:>4}'
        )

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfAcceleratedRound(
            match_points=float_or_default(match.group('match_points')),
            game_points=float_or_default(match.group('game_points')),
            first_round=int(match.group('first_round')),
            last_round=int(match.group('last_round')),
            first_id=int(match.group('first_id')),
            last_id=int(match.group('last_id')),
        )


class ProhibitedPairingEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<first_round>[ \d]{3}) (?P<last_round>[ \d]{3})'
        r'(?P<pairing_numbers>( [ \d]{4}){2,})\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('260', 'prohibited_pairings')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'RRF RRL'
        num_columns = max(
            len(pairing.pairing_numbers) for pairing in tournament.prohibited_pairings
        )
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        pairing: TrfProhibitedPairing = value
        line = f'{pairing.first_round:>3} {pairing.last_round or "":>3}'
        for pairing_number in pairing.pairing_numbers:
            line += f' {pairing_number:>4}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfProhibitedPairing(
            first_round=int(match.group('first_round')),
            last_round=int_or_default(match.group('last_round')),
            pairing_numbers=split_ints(match.group('pairing_numbers'), 5),
        )


class RoundByeEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<type>[fhz]) (?P<round>[ \d]{3})'
        r'(?P<pairing_numbers>( [ \d]{4})+)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('240', 'round_byes')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'T RRR'
        num_columns = max(len(bye.pairing_numbers) for bye in tournament.round_byes)
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        bye: TrfRoundBye = value
        line = f'{bye.type:1} {bye.round:>3}'
        for pairing_number in bye.pairing_numbers:
            line += f' {pairing_number:>4}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfRoundBye(
            type=match.group('type'),
            round=int(match.group('round')),
            pairing_numbers=split_ints(match.group('pairing_numbers'), 5),
        )


class TeamPABsEntry(SingleLineEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<match_points>[ \d.]{4}) (?P<game_points>[ \d.]{4})'
        r'(?P<team_ids>( [ \d]{3})*)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('320', 'team_pabs')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'MMMM GGGG'
        assert tournament.team_pabs is not None
        num_columns = len(tournament.round_dates)
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(3, "R")}'
        return header

    def format(self, value: Any) -> str:
        team_pabs: TrfTeamPABs = value
        line = (
            f'{float_display(team_pabs.match_points, 4)} '
            f'{float_display(team_pabs.game_points, 4)}'
        )
        for round_ in range(1, max(team_pabs.team_id_by_round) + 1):
            team_id = team_pabs.team_id_by_round.get(round_, None)
            line += f' {team_id or "":>3}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)

        teams_ids = split_optional_ints(match.group('team_ids'), 4)
        team_id_by_round: dict[int, int] = {}
        for round_, team_id in enumerate(teams_ids, start=1):
            if team_id:
                team_id_by_round[round_] = team_id
        return TrfTeamPABs(
            match_points=float(match.group('match_points')),
            game_points=float(match.group('game_points')),
            team_id_by_round=team_id_by_round,
        )


class TeamForfeitedMatchEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<type>[-+]{2}) (?P<round>[ \d]{3}) '
        r'(?P<white_team_id>[ \d]{3}) (?P<black_team_id>[ \d]{3})\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('330', 'team_forfeited_matches')

    def get_header(self, tournament: TrfTournament) -> str | None:
        return 'TT RRR WWW BBB'

    def format(self, value: Any) -> str:
        match: TrfTeamForfeitedMatch = value
        return (
            f'{match.type:>2} {match.round:>3} '
            f'{match.white_team_id:>3} {match.black_team_id:>3}'
        )

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)

        return TrfTeamForfeitedMatch(
            type=match.group('type'),
            round=int(match.group('round')),
            white_team_id=int(match.group('white_team_id')),
            black_team_id=int(match.group('black_team_id')),
        )


class OOdOTeamPairingEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<round>[ \d]{3}) (?P<team_id>[ \d]{3}) '
        r'(?P<opponent_team_id>[ \d]{3})(?P<boards>( [ \d]{4})*)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('300', 'oodo_team_pairings')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'RRR TT1 TT2'
        num_columns = max(
            len(pairing.boards) for pairing in tournament.oodo_team_pairings
        )
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        pairing: TrfOOdOTeamPairing = value
        line = f'{pairing.round:>3} {pairing.team_id:>3} {pairing.opponent_team_id:>3}'
        for board in pairing.boards:
            line += f' {board or "0000":>4}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfOOdOTeamPairing(
            round=int(match.group('round')),
            team_id=int(match.group('team_id')),
            opponent_team_id=int(match.group('opponent_team_id')),
            boards=split_optional_ints(match.group('boards'), 5),
        )


class AbnormalPointsAssignmentEntry(MultipleLinesEntry):
    LINE_PATTERN = re.compile(
        r'^(?P<type>[dwlfhz+\- ]) (?P<match_points>[ \-\d.]{4}) '
        r'(?P<game_points>[ \-\d.]{4})(?P<round>(\s[ \d]{3})?)(?P<pairing_numbers>( [ \d]{4})*)\s*$',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__('299', 'abnormal_points_assignments')

    def get_header(self, tournament: TrfTournament) -> str | None:
        header = 'T MMMM GGGG RRR'
        num_columns = max(
            len(assignment.pairing_numbers)
            for assignment in tournament.abnormal_points_assignments
        )
        for column in range(1, num_columns + 1):
            header += f' {str(column).rjust(4, "P")}'
        return header

    def format(self, value: Any) -> str:
        assignment: TrfAbnormalPointsAssignment = value
        line = (
            f'{assignment.type:1}'
            f' {float_display(assignment.match_points, 4)}'
            f' {float_display(assignment.game_points, 4)}'
            f' {assignment.round or "000":3}'
        )
        for pairing_number in assignment.pairing_numbers:
            line += f' {pairing_number or "0000":>4}'
        return line

    def parse(self, data: str) -> Any:
        match = self.LINE_PATTERN.fullmatch(data)
        if match is None:
            raise self.line_exception(data)
        return TrfAbnormalPointsAssignment(
            type=match.group('type'),
            match_points=float_or_default(match.group('match_points')),
            game_points=float_or_default(match.group('game_points')),
            round=int_or_default(match.group('round')),
            pairing_numbers=split_optional_ints(match.group('pairing_numbers'), 5),
        )


class InformativeTeamPairingsEntry(MultipleLinesEntry):
    """This entry is informative, it does not require being read."""

    def __init__(self):
        super().__init__('801', 'informative_team_pairings_records')

    def get_header(self, tournament: TrfTournament) -> str | None:
        return 'Team pairings'


class InformativeTeamResultsEntry(MultipleLinesEntry):
    """This entry is informative, it does not require being read."""

    def __init__(self):
        super().__init__('802', 'informative_team_results_records')

    def get_header(self, tournament: TrfTournament) -> str | None:
        return 'Team results'


ENTRIES = [
    SingleLineEntry('012', 'name'),
    SingleLineEntry('022', 'city'),
    SingleLineEntry('032', 'federation'),
    SingleLineEntry('042', 'start_date'),
    SingleLineEntry('052', 'end_date'),
    SingleLineIntEntry('062', 'num_players'),
    SingleLineIntEntry('072', 'num_rated_players'),
    SingleLineIntEntry('082', 'num_teams'),
    SingleLineEntry('092', 'type'),
    SingleLineEntry('102', 'chief_arbiter'),
    MultipleLinesEntry('112', 'deputy_arbiters'),
    SingleLineEntry('122', 'allotted_time'),
    RoundDatesEntry(),
    SingleLineIntEntry('142', 'num_rounds'),
    SingleLineEntry('152', 'initial_color'),
    PointSystemEntry('162', 'individuals_point_system'),
    SingleLineEntry('172', 'starting_rank_method'),
    SingleLineEntry('182', 'pairing_controller_id'),
    SingleLineEntry('192', 'encoded_type'),
    SingleLineListEntry('202', 'tie_breaks'),
    SingleLineListEntry('212', 'standings_tie_breaks'),
    SingleLineEntry('222', 'time_control'),
    SingleLineEntry('352', 'board_color_sequence'),
    PointSystemEntry('362', 'teams_point_system'),
    PlayerEntry(),
    TeamEntry(),
    RoundByeEntry(),
    AcceleratedRoundEntry(),
    ProhibitedPairingEntry(),
    TeamPABsEntry(),
    TeamForfeitedMatchEntry(),
    OOdOTeamPairingEntry(),
    AbnormalPointsAssignmentEntry(),
    InformativeTeamPairingsEntry(),
    InformativeTeamResultsEntry(),
    DeprecatedTeamEntry(),
]
