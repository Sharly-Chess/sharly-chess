import contextlib
import html
import re
import unicodedata
from collections import Counter
from urllib.parse import urlencode
from dataclasses import dataclass, field
from logging import Logger

from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag

from common.exception import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from data.board import Board
from data.pairings.fixed_table import FixedTablePairingEngine
from data.player import Player
from data.teams.team import Team
from data.teams.team_board import TeamBoard
from data.tournament import Tournament
from plugins.ffe.ffe_session import (
    FFESession,
    FFE_ADMIN_URL,
    VIEW_STATE_INPUT_ID,
    VIEW_STATE_GENERATOR_INPUT_ID,
    EVENT_VALIDATION_INPUT_ID,
)
from plugins.ffe.ffe_upload_status import (
    FailureFFEUploadStatus,
    NotReachableFFEUploadStatus,
    AuthFailureFFEUploadStatus,
    GroupNotFoundFFEUploadStatus,
    RejectedFFEUploadStatus,
    UnexpectedFailureFFEUploadStatus,
)
from plugins.ffe.utils import FFEUtils
from utils.enum import Result, ScoreType

logger: Logger = get_logger()

EQUIPES_URL: str = FFE_ADMIN_URL + '/Equipes.aspx'
TEAM_FORM_URL: str = FFE_ADMIN_URL + '/FicheEquipe.aspx'
PV_FORM_URL: str = FFE_ADMIN_URL + '/FichePV.aspx'
AUTOCOMPLETE_URL: str = FFE_ADMIN_URL + '/AutoComplete.ashx'

MAIN: str = 'ctl00$ContentPlaceHolderMain$'
MAIN_ID: str = 'ctl00_ContentPlaceHolderMain_'
LOGOUT_LINK_ID: str = 'ctl00_CmdDeconnection'
MESSAGE_LABEL_ID: str = MAIN_ID + 'LabelMessage'
COMPETITION_SELECT: str = MAIN + 'SelectCompetition'
DIVISION_SELECT: str = MAIN + 'SelectDivision'
GROUP_SELECT: str = MAIN + 'SelectGroupe'
PV_TABLE_ID: str = 'TablePV'
TEAM_FORM_TITLE_ID: str = MAIN_ID + 'LabelEquipeTitre'
PV_FORM_TITLE_ID: str = MAIN_ID + 'LabelPV'

CREATE_TEAM_EVENT: str = MAIN + 'LinkCmdEquipeCreer'
SAVE_TEAM_EVENT: str = MAIN + 'CmdEquipeSave'
DELETE_TEAM_EVENT: str = MAIN + 'CmdEquipeDelete'
CREATE_PV_EVENT: str = MAIN + 'LinkCmdPVCreer'
SAVE_PV_EVENT: str = MAIN + 'LinkCmdSave'
DELETE_PV_EVENT: str = MAIN + 'LinkCmdDelete'
STANDINGS_EVENT: str = MAIN + 'LinkCmdClassement'

# Board results of the match report, from the perspective of the team
# listed on the left ("Blanc"), whatever the colours on the board.
SITE_RESULTS: dict[Result, str] = {
    Result.NO_RESULT: 'None',
    Result.WIN: 'GainBlanc',
    Result.LOSS: 'GainNoir',
    Result.DRAW: 'Nulle',
    Result.FORFEIT_WIN: 'GainBlancForfait',
    Result.FORFEIT_LOSS: 'GainNoirForfait',
    Result.DOUBLE_FORFEIT: 'DoubleForfait',
    Result.UNRATED_WIN: 'GainBlanc',
    Result.UNRATED_LOSS: 'GainNoir',
    Result.UNRATED_DRAW: 'Nulle',
    Result.PENALTY_LL: 'DoubleDefaite',
    Result.UNRATED_PENALTY_LL: 'DoubleDefaite',
}
UNMAPPED_SITE_RESULT: str = 'NonAttribue'


def site_name_key(name: str) -> str:
    """The site re-cases the names it stores and drops their accents:
    names are compared through this key."""
    stripped = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return ' '.join(stripped.casefold().split())


@dataclass(frozen=True)
class SiteOption:
    """One ``<option>`` of a site select: a division or a group."""

    id: int
    name: str


@dataclass(frozen=True)
class SiteMatchReport:
    """One match report (PV) as listed on the group page. The team names
    are empty on a blank report."""

    id: int
    round: int
    left_team_name: str
    right_team_name: str

    @property
    def is_blank(self) -> bool:
        return not self.left_team_name and not self.right_team_name


@dataclass
class GroupPage:
    """The group's page in the team module, parsed."""

    teams_by_name: dict[str, int] = field(default_factory=dict)
    match_reports: list[SiteMatchReport] = field(default_factory=list)

    @property
    def report_ids(self) -> set[int]:
        return {report.id for report in self.match_reports}


@dataclass(frozen=True)
class Match:
    """A team-vs-team match of a round: the envelope of a team board, or
    the boards two teams share in a round of a fixed-table system
    (Molter), which pairs the players directly."""

    round: int
    team_a: Team
    team_b: Team
    boards: list[Board]
    game_points: tuple[float, float]
    match_points: tuple[float, float]

    @property
    def played(self) -> bool:
        """Whether any board has a result: the site gets scores for a
        played match only."""
        return any(not board.no_result for board in self.boards)

    def board_team_ids(self, board: Board) -> tuple[int | None, int | None]:
        """``(white_team_id, black_team_id)``; a forfeited side is a hole
        and takes the match's other team."""
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        white_team_id = white.team_id if white else None
        black_team_id = black.team_id if black else None
        if white_team_id is None and black_team_id is not None:
            white_team_id = (
                self.team_a.id if black_team_id == self.team_b.id else self.team_b.id
            )
        elif black_team_id is None and white_team_id is not None:
            black_team_id = (
                self.team_a.id if white_team_id == self.team_b.id else self.team_b.id
            )
        return white_team_id, black_team_id

    @classmethod
    def from_team_board(cls, team_board: TeamBoard) -> 'Match | None':
        team_b = team_board.team_b
        if team_b is None:
            return None
        return cls(
            round=team_board.round,
            team_a=team_board.team_a,
            team_b=team_b,
            boards=team_board.boards,
            game_points=team_board.effective_game_points,
            match_points=team_board.match_points_pair() or (0.0, 0.0),
        )

    @classmethod
    def from_boards(
        cls,
        tournament: Tournament,
        round_: int,
        team_a: Team,
        team_b: Team,
        boards: list[Board],
        adjustments: tuple[float, float] = (0.0, 0.0),
    ) -> 'Match':
        """The match two teams play over *boards*, scored like a team
        board: the tournament's team game points, plus the teams' point
        *adjustments* for the match, then match points from the result."""
        a_gp, b_gp = adjustments
        team_game_points = tournament.team_game_points
        for board in boards:
            white = board.optional_white_tournament_player
            black = board.black_tournament_player
            white_pts = (
                board.white_pairing.result.points(team_game_points) if white else 0.0
            )
            black_pts = (
                board.black_pairing.result.points(team_game_points) if black else 0.0
            )
            if (white.team_id if white else None) == team_a.id or (
                black.team_id if black else None
            ) == team_b.id:
                a_gp += white_pts
                b_gp += black_pts
            else:
                a_gp += black_pts
                b_gp += white_pts
        mp = tournament.match_points
        win_mp = mp.get(Result.WIN, 2.0)
        draw_mp = mp.get(Result.DRAW, 1.0)
        loss_mp = mp.get(Result.LOSS, 0.0)
        if a_gp > b_gp:
            match_points = (win_mp, loss_mp)
        elif a_gp < b_gp:
            match_points = (loss_mp, win_mp)
        else:
            match_points = (draw_mp, draw_mp)
        return cls(round_, team_a, team_b, boards, (a_gp, b_gp), match_points)


@dataclass
class MatchReportData:
    """What Sharly posts for one match: teams, boards, scores."""

    round: int
    number: int
    left_team_id: int
    right_team_id: int
    left_match_points: str
    right_match_points: str
    left_game_points: str
    right_game_points: str
    boards: list[tuple[str, str, str]]  # (left licence, right licence, site result)
    left_captain: str
    right_captain: str
    date: str
    place: str
    arbiter: str


class FFETeamSession(FFESession):
    """A session on the team module of the FFE admin website, where team
    competitions are managed through match reports (one per round and
    pair of teams) rather than through Papi files."""

    def __init__(self, tournament: Tournament | None):
        super().__init__(tournament)
        self.competition_id: int | None = None
        self.division_id: int | None = None
        self.group_id: int | None = None

    # ---------------------------------------------------------------------
    # Static checks
    # ---------------------------------------------------------------------

    @staticmethod
    def licence_number(player: Player) -> str | None:
        return FFEUtils.get_player_plugin_data(player).ffe_licence_number or None

    @classmethod
    def upload_unavailable_message(cls, tournament: Tournament) -> str | None:
        """Why the tournament cannot be sent to the team module, or None.
        Every player on a paired board needs a licence number: the site
        identifies players by it and nothing else."""
        unlicensed: list[str] = []
        for board in tournament.boards_by_id.values():
            for player in (
                board.optional_white_tournament_player,
                board.black_tournament_player,
            ):
                if player is None or cls.licence_number(player):
                    continue
                name = player.full_name
                if name not in unlicensed:
                    unlicensed.append(name)
        if unlicensed:
            names = ', '.join(unlicensed[:3])
            if len(unlicensed) > 3:
                names += ', …'
            return _('Players without FFE licence number: {names}.').format(names=names)
        for team in tournament.teams:
            if cls._correspondent_licence(team) is None:
                return _(
                    'Team [{team}] has no player with an FFE licence number.'
                ).format(team=team.name)
        return None

    @classmethod
    def _correspondent_licence(cls, team: Team) -> str | None:
        """The licence the team is registered under on the site: its
        captain's, else the first roster player's."""
        players = ([team.captain] if team.captain else []) + team.players
        for player in players:
            if licence := cls.licence_number(player):
                return licence
        return None

    # ---------------------------------------------------------------------
    # Site access
    # ---------------------------------------------------------------------

    def _post(self, url: str, data: dict[str, str]) -> AdvancedHTMLParser | None:
        """Posts a WebForms postback (state variables plus *data*) and
        returns the page that follows, with the state read from it."""
        post_data: dict[str, str] = {
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        post_data.update(data)
        html = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return None
        parser, error = self._parse_html_content(html)
        if error or parser is None:
            return None
        if not self.read_ffe_state(parser, url, admin=True):
            return None
        return parser

    def _get(self, url: str) -> AdvancedHTMLParser | None:
        html = self._read_url(url=url, data=None, files=None)
        if not html:
            return None
        parser, error = self._parse_html_content(html)
        if error or parser is None:
            return None
        if not self.read_ffe_state(parser, url, admin=True):
            return None
        return parser

    def login(self, login: str, password: str) -> bool | None:
        """Logs in with a group account. Returns True on success, False
        when the credentials are refused, None when the site could not
        be reached."""
        if not self._ffe_init(admin=True):
            return None
        parser = self._ffe_login(login, password)
        if parser is None:
            return None
        if parser.getElementById(LOGOUT_LINK_ID) is None:
            logger.error('Authentication failed.')
            return False
        logger.debug('FFE authentication succeeded.')
        return True

    def _selects_data(self) -> dict[str, str]:
        data = {COMPETITION_SELECT: str(self.competition_id)}
        if self.division_id:
            data[DIVISION_SELECT] = str(self.division_id)
        if self.group_id:
            data[GROUP_SELECT] = str(self.group_id)
        return data

    def _select(self, target: str) -> AdvancedHTMLParser | None:
        """Fires the change postback of one of the three selects."""
        return self._post(EQUIPES_URL, {'__EVENTTARGET': target} | self._selects_data())

    @staticmethod
    def _options(parser: AdvancedHTMLParser, select_name: str) -> list[SiteOption]:
        select = parser.getElementsByAttr('name', select_name)
        if not select:
            return []
        options: list[SiteOption] = []
        for option in select[0].children:
            if option.tagName != 'option':
                continue
            value = option.getAttribute('value') or ''
            if not value.isdigit() or value == '1':
                # ``1`` is the "select a …" placeholder.
                continue
            options.append(SiteOption(int(value), (option.innerText or '').strip()))
        return options

    def list_divisions(self, competition_id: int) -> list[SiteOption] | None:
        """The divisions of the competition, or None when the site
        could not be read."""
        self.competition_id = competition_id
        self.division_id = self.group_id = None
        if self._get(EQUIPES_URL) is None:
            return None
        parser = self._select(COMPETITION_SELECT)
        if parser is None:
            return None
        return self._options(parser, DIVISION_SELECT)

    def list_groups(
        self, competition_id: int, division_id: int
    ) -> list[SiteOption] | None:
        """The groups of the division, or None when the site could not
        be read."""
        if self.list_divisions(competition_id) is None:
            return None
        self.division_id = division_id
        parser = self._select(DIVISION_SELECT)
        if parser is None:
            return None
        return self._options(parser, GROUP_SELECT)

    def open_group(
        self, competition_id: int, division_id: int, group_id: int
    ) -> GroupPage | None:
        """Selects the group and parses its page, or returns None when
        the site could not be read. Raises a SharlyChessException when
        the group is not listed (or the account has no rights on it)."""
        groups = self.list_groups(competition_id, division_id)
        if groups is None:
            return None
        if group_id not in {group.id for group in groups}:
            raise SharlyChessException(
                f'Group [{group_id}] not found in division [{division_id}] '
                f'of competition [{competition_id}].'
            )
        self.group_id = group_id
        parser = self._select(GROUP_SELECT)
        if parser is None:
            return None
        page = self.parse_group_page(parser)
        if page is None:
            raise SharlyChessException(
                f'Group [{group_id}] cannot be edited with this account.'
            )
        return page

    # ---------------------------------------------------------------------
    # Page parsing
    # ---------------------------------------------------------------------

    @staticmethod
    def _descendants(tag: AdvancedTag, tag_name: str) -> list[AdvancedTag]:
        return [node for node in tag.getAllChildNodes() if node.tagName == tag_name]

    @staticmethod
    def _href_id(tag: AdvancedTag, page: str) -> int | None:
        href = tag.getAttribute('href') or ''
        if not href.startswith(page):
            return None
        match = re.search(r'[?&]Id=(\d+)', href)
        return int(match.group(1)) if match else None

    @classmethod
    def parse_group_page(cls, parser: AdvancedHTMLParser) -> GroupPage | None:
        """Parses the teams and match reports of a group page, or returns
        None when the page holds no editor (no rights on the group)."""
        pv_table = parser.getElementById(PV_TABLE_ID)
        if pv_table is None or parser.getElementById(MAIN_ID + 'CellMenuPv') is None:
            return None
        page = GroupPage()
        for anchor in parser.getElementsByTagName('a'):
            team_id = cls._href_id(anchor, 'FicheEquipe.aspx')
            if team_id is not None:
                page.teams_by_name[(anchor.innerText or '').strip()] = team_id
        round_: int | None = None
        for row in cls._descendants(pv_table, 'tr'):
            report_id: int | None = None
            names: dict[str, str] = {}
            for anchor in cls._descendants(row, 'a'):
                href = anchor.getAttribute('href') or ''
                if match := re.search(r'GroupeCalendrier\.aspx\?.*Rd=(\d+)', href):
                    round_ = int(match.group(1))
                elif (pv_id := cls._href_id(anchor, 'FichePV.aspx')) is not None:
                    report_id = pv_id
                else:
                    anchor_id = anchor.getAttribute('id') or ''
                    for side in ('Bl', 'Nr'):
                        if anchor_id.endswith(f'LinkCmdCopier{side}'):
                            text = html.unescape(anchor.innerText or '')
                            names[side] = text.replace('\xa0', ' ').strip()
            if report_id is not None and round_ is not None:
                page.match_reports.append(
                    SiteMatchReport(
                        report_id, round_, names.get('Bl', ''), names.get('Nr', '')
                    )
                )
        return page

    @staticmethod
    def _message(parser: AdvancedHTMLParser) -> str:
        tag = parser.getElementById(MESSAGE_LABEL_ID)
        return (tag.innerText or '').strip() if tag else ''

    @staticmethod
    def parse_board_count(parser: AdvancedHTMLParser) -> int:
        """The number of board rows of a match report form."""
        return len(
            [
                select
                for select in parser.getElementsByTagName('select')
                if (select.getAttribute('name') or '').endswith('$DropDownResult')
            ]
        )

    # ---------------------------------------------------------------------
    # Autocomplete
    # ---------------------------------------------------------------------

    def find_club(self, name: str) -> str | None:
        """The site's ``CODE - name`` label of the club called *name*,
        as the team form expects it, or None when not found. The search
        chokes on apostrophes, so it runs on the longest apostrophe-free
        part of the name and the reply is matched against the whole."""
        fragment = max(name.split("'"), key=len).strip()
        query = urlencode({'action': 'cb', 'q': fragment, 'limit': 10})
        html = self._read_url(url=f'{AUTOCOMPLETE_URL}?{query}', data=None, files=None)
        if not html:
            return None
        lines = [line.strip() for line in html.splitlines() if line.strip()]
        for line in lines:
            if line.split(' - ', 1)[-1].strip().casefold() == name.strip().casefold():
                return line
        return lines[0] if len(lines) == 1 else None

    # ---------------------------------------------------------------------
    # Writes
    # ---------------------------------------------------------------------

    def create_team(self, team: Team, number: int) -> GroupPage:
        """Registers the team in the group and returns the group page the
        site comes back to. Raises a SharlyChessException when the site
        refuses it."""
        logger.info('Creating team [%s] on the FFE website...', team.name)
        if self._select_action(CREATE_TEAM_EVENT) is None:
            raise SharlyChessException('The team form could not be opened.')
        return self._save_team(team, number)

    def delete_team(self, site_id: int) -> GroupPage | None:
        """Deletes a team of the group, or returns None when the site
        refuses (a team with reports cannot be deleted)."""
        logger.info('Deleting team [%d] on the FFE website...', site_id)
        form_url = f'{TEAM_FORM_URL}?Id={site_id}&saison='
        if self._get(form_url) is None:
            return None
        parser = self._post(form_url, {'__EVENTTARGET': DELETE_TEAM_EVENT})
        if parser is None or parser.getElementById(TEAM_FORM_TITLE_ID) is not None:
            return None
        return self.parse_group_page(parser)

    def _save_team(self, team: Team, number: int) -> GroupPage:
        assert self.group_id is not None
        club = self._team_club(team)
        form_url = f'{TEAM_FORM_URL}?Id=0&Groupe={self.group_id}&saison='
        parser = self._post(
            form_url,
            {
                '__EVENTTARGET': SAVE_TEAM_EVENT,
                MAIN + 'TextGroupeId': str(self.group_id),
                MAIN + 'TextEquipeNom': team.name[:50],
                MAIN + 'DropEquipeNr$DropDownNumeric': str(number),
                MAIN + 'TextClub': club or '',
                MAIN + 'TextCorrespondant': self._correspondent_licence(team) or '',
                MAIN + 'TextEquipeCommentaire': '',
                MAIN + 'DropEquipeJoue$DropDownNumeric': '',
                MAIN + 'DropEquipePtsMatch$DropDownNumeric': '',
                MAIN + 'DropEquipePtsPour$DropDownDecimal': '',
                MAIN + 'DropEquipePtsContre$DropDownDecimal': '',
                MAIN + 'DropEquipePtsDiff$DropDownDecimal': '',
                MAIN + 'DropEquipePlace$DropDownNumeric': '',
                MAIN + 'DropInscriptionDu$DropDownNumeric': '',
            },
        )
        if parser is None:
            raise SharlyChessException('The team form could not be saved.')
        if parser.getElementById(TEAM_FORM_TITLE_ID) is not None:
            raise SharlyChessException(
                f'Team [{team.name}] refused: {self._message(parser)}'
            )
        page = self.parse_group_page(parser)
        if page is None:
            raise SharlyChessException('The group page could not be read back.')
        return page

    def _select_action(self, target: str) -> AdvancedHTMLParser | None:
        """Fires an action link of the group page (the page must be the
        one last read)."""
        return self._post(
            EQUIPES_URL,
            {
                '__EVENTTARGET': target,
                MAIN + 'DropDateRondeNr$DropDownNumeric': '0',
                MAIN + 'TextDateDefault': '',
                MAIN + 'TextLieuDefault': '',
            }
            | self._selects_data(),
        )

    def _team_club(self, team: Team) -> str | None:
        clubs = Counter(player.club.name for player in team.players if player.club.name)
        if not clubs:
            return None
        name = clubs.most_common(1)[0][0]
        club = self.find_club(name)
        if club is None:
            logger.warning(
                'Club [%s] of team [%s] not found on the FFE website.', name, team.name
            )
        return club

    def create_blank_report(self, page: GroupPage) -> int:
        """Creates a blank match report and returns its id. Raises a
        SharlyChessException when the site refuses it."""
        parser = self._select_action(CREATE_PV_EVENT)
        if parser is None:
            raise SharlyChessException('The match report could not be created.')
        new_page = self.parse_group_page(parser)
        if new_page is None:
            raise SharlyChessException('The group page could not be read back.')
        created = new_page.report_ids - page.report_ids
        if len(created) != 1:
            raise SharlyChessException(
                f'Unexpected match reports after creation: {sorted(created)}.'
            )
        page.match_reports = new_page.match_reports
        return created.pop()

    def save_report(self, report_id: int, data: MatchReportData) -> GroupPage:
        """Fills in and saves a match report and returns the group page
        the site comes back to. Raises a SharlyChessException when the
        site refuses it."""
        form_url = f'{PV_FORM_URL}?saison=&Id={report_id}'
        parser = self._get(form_url)
        if parser is None:
            raise SharlyChessException(
                f'Match report [{report_id}] could not be opened.'
            )
        board_count = self.parse_board_count(parser)
        if len(data.boards) > board_count:
            logger.warning(
                'Match report [%d] has %d boards, %d in Sharly Chess: the extra boards are not sent.',
                report_id,
                board_count,
                len(data.boards),
            )
        post_data: dict[str, str] = {
            '__EVENTTARGET': SAVE_PV_EVENT,
            MAIN + 'DropRonde$DropDownNumeric': str(data.round),
            MAIN + 'DropNr$DropDownNumeric': str(data.number),
            MAIN + 'TextDatePV': data.date,
            MAIN + 'TextLieu': data.place[:50],
            MAIN + 'TextArbitre': data.arbiter,
            MAIN + 'DropPtsMatchBl$DropDownNumeric': data.left_match_points,
            MAIN + 'DropDownEquipeBlanc': str(data.left_team_id),
            MAIN + 'DropPtsBl$DropDownDecimal': data.left_game_points,
            MAIN + 'DropPtsNr$DropDownDecimal': data.right_game_points,
            MAIN + 'DropDownEquipeNoir': str(data.right_team_id),
            MAIN + 'DropPtsMatchNr$DropDownNumeric': data.right_match_points,
            MAIN + 'TextCapitaineBl': data.left_captain,
            MAIN + 'TextCapitaineNr': data.right_captain,
        }
        for index in range(board_count):
            left, right, result = (
                data.boards[index] if index < len(data.boards) else ('', '', 'None')
            )
            prefix = f'{MAIN}RepeaterBoards$ctl{index:02d}$'
            post_data[prefix + 'TextNrFFEBl'] = left
            post_data[prefix + 'TextNrFFENr'] = right
            post_data[prefix + 'DropDownResult'] = result
        parser = self._post(form_url, post_data)
        if parser is None:
            raise SharlyChessException(
                f'Match report [{report_id}] could not be saved.'
            )
        if parser.getElementById(PV_FORM_TITLE_ID) is not None:
            raise SharlyChessException(
                f'Match report [{report_id}] refused: {self._message(parser)}'
            )
        page = self.parse_group_page(parser)
        if page is None:
            raise SharlyChessException('The group page could not be read back.')
        return page

    def delete_report(self, report_id: int) -> GroupPage:
        """Deletes a match report and returns the group page the site
        comes back to. Raises a SharlyChessException when it fails."""
        logger.info('Deleting match report [%d] on the FFE website...', report_id)
        form_url = f'{PV_FORM_URL}?saison=&Id={report_id}'
        if self._get(form_url) is None:
            raise SharlyChessException(
                f'Match report [{report_id}] could not be opened.'
            )
        parser = self._post(form_url, {'__EVENTTARGET': DELETE_PV_EVENT})
        if parser is None:
            raise SharlyChessException(
                f'Match report [{report_id}] could not be deleted.'
            )
        page = self.parse_group_page(parser)
        if page is None:
            raise SharlyChessException('The group page could not be read back.')
        return page

    def recompute_standings(self) -> None:
        if self._select_action(STANDINGS_EVENT) is None:
            logger.warning('The standings could not be recomputed on the FFE website.')

    def set_team_places(self, site_team_ids: dict[int, int]) -> None:
        """Writes Sharly's ranks into the teams' *Place* field: the site
        ranks on points, differential and points "for" only, and leaves
        the teams it cannot separate in arbitrary order. Run after
        :meth:`recompute_standings`, which rewrites the cards' figures."""
        assert self.tournament is not None
        for standing in self.tournament.team_standings():
            site_id = site_team_ids.get(standing.team.id)
            if site_id is None:
                continue
            form_url = f'{TEAM_FORM_URL}?Id={site_id}&saison='
            parser = self._get(form_url)
            if parser is None:
                logger.warning('Team card [%d] could not be opened.', site_id)
                continue
            data = self._form_values(parser)
            if data.get(MAIN + 'DropEquipePlace$DropDownNumeric') == str(standing.rank):
                continue
            data[MAIN + 'DropEquipePlace$DropDownNumeric'] = str(standing.rank)
            data['__EVENTTARGET'] = SAVE_TEAM_EVENT
            parser = self._post(form_url, data)
            if parser is None or parser.getElementById(TEAM_FORM_TITLE_ID) is not None:
                logger.warning(
                    'Place of team [%s] could not be set on the FFE website: %s',
                    standing.team.name,
                    self._message(parser) if parser else '',
                )

    @staticmethod
    def _form_values(parser: AdvancedHTMLParser) -> dict[str, str]:
        """The values a form would submit as it stands: text inputs and
        the selected option of every select, disabled ones left out."""
        values: dict[str, str] = {}
        for tag in parser.getElementsByTagName('input'):
            name = tag.getAttribute('name') or ''
            if not name or name.startswith('__') or tag.hasAttribute('disabled'):
                continue
            if (tag.getAttribute('type') or 'text') in ('text', 'hidden', 'password'):
                values[name] = tag.getAttribute('value') or ''
        for tag in parser.getElementsByTagName('textarea'):
            name = tag.getAttribute('name') or ''
            if name and not tag.hasAttribute('disabled'):
                values[name] = html.unescape(tag.innerText or '')
        for tag in parser.getElementsByTagName('select'):
            name = tag.getAttribute('name') or ''
            if not name or tag.hasAttribute('disabled'):
                continue
            values[name] = next(
                (
                    option.getAttribute('value') or ''
                    for option in tag.children
                    if option.tagName == 'option' and option.hasAttribute('selected')
                ),
                '',
            )
        return values

    # ---------------------------------------------------------------------
    # Tournament → match reports
    # ---------------------------------------------------------------------

    @classmethod
    def round_matches(cls, tournament: Tournament, round_: int) -> list[Match]:
        """The matches of the round: its team boards, or — in a system
        pairing players across teams without match envelopes — the
        boards of each pair of teams, in board order."""
        team_boards = tournament.get_round_team_boards(round_)
        if team_boards:
            return [
                match
                for team_board in team_boards
                if (match := Match.from_team_board(team_board)) is not None
            ]
        teams_by_id = tournament.teams_by_id
        engine = tournament.pairing_variation.engine
        table_teams = (
            engine.round_board_teams(tournament, round_)
            if isinstance(engine, FixedTablePairingEngine)
            else {}
        )
        boards_by_pair: dict[tuple[int, int], list[Board]] = {}
        for board in tournament.get_round_boards(round_):
            white = board.optional_white_tournament_player
            black = board.black_tournament_player
            white_team_id = white.team_id if white else None
            black_team_id = black.team_id if black else None
            if (white_team_id is None or black_team_id is None) and (
                seats := table_teams.get(board.index)
            ):
                # A hole: the table says which team left the seat empty.
                white_team_id, black_team_id = seats[0].id, seats[1].id
            if white_team_id is None or black_team_id is None:
                continue
            pair = (white_team_id, black_team_id)
            if pair[::-1] in boards_by_pair:
                pair = pair[::-1]
            boards_by_pair.setdefault(pair, []).append(board)
        # The split of a round into reports is the site's, not the
        # cup's: a team's round adjustment (a forfeit penalty, a manual
        # bonus) is spread over its reports so that none goes below
        # zero when the round as a whole allows it, the reports with
        # forfeited boards first; a bonus lands on its first report.
        raw = {
            pair: Match.from_boards(
                tournament, round_, teams_by_id[a], teams_by_id[b], boards
            )
            for (a, b), boards in boards_by_pair.items()
            for pair in [(a, b)]
        }
        forfeits: dict[tuple[int, tuple[int, int]], int] = {}
        for pair, boards in boards_by_pair.items():
            for board in boards:
                for team_id in cls._forfeiting_team_ids(board, pair, table_teams):
                    forfeits[(team_id, pair)] = forfeits.get((team_id, pair), 0) + 1
        adjustments: dict[tuple[int, int], list[float]] = {
            pair: [0.0, 0.0] for pair in boards_by_pair
        }
        for team_id in {team_id for pair in boards_by_pair for team_id in pair}:
            _mp, gp = tournament.point_adjustments.effective(team_id, round_)
            if not gp:
                continue
            team_pairs = sorted(
                (pair for pair in boards_by_pair if team_id in pair),
                key=lambda pair: -forfeits.get((team_id, pair), 0),
            )
            if gp > 0:
                adjustments[team_pairs[0]][team_pairs[0].index(team_id)] += gp
                continue
            remaining = -gp
            for pair in team_pairs:
                side = pair.index(team_id)
                absorbed = min(remaining, max(raw[pair].game_points[side], 0.0))
                adjustments[pair][side] -= absorbed
                remaining -= absorbed
            if remaining:
                adjustments[team_pairs[0]][team_pairs[0].index(team_id)] -= remaining
        return [
            Match.from_boards(
                tournament,
                round_,
                teams_by_id[a],
                teams_by_id[b],
                boards,
                (adjustments[(a, b)][0], adjustments[(a, b)][1]),
            )
            for (a, b), boards in boards_by_pair.items()
        ]

    @staticmethod
    def _forfeiting_team_ids(
        board: Board,
        pair: tuple[int, int],
        table_teams: dict[int, tuple[Team, Team]],
    ) -> list[int]:
        """The teams that forfeited *board*: an empty seat, or a player
        with a forfeit loss."""
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        seats = table_teams.get(board.index)
        forfeiting: list[int] = []
        for player, seat, pairing in (
            (white, 0, board.optional_white_pairing),
            (black, 1, board.optional_black_pairing),
        ):
            if player is None:
                if seats is not None:
                    forfeiting.append(seats[seat].id)
                continue
            result = pairing.result if pairing else Result.NO_RESULT
            if (
                result in (Result.FORFEIT_LOSS, Result.DOUBLE_FORFEIT)
                and player.team_id in pair
            ):
                forfeiting.append(player.team_id)
        return forfeiting

    @classmethod
    def match_report_data(
        cls,
        match: Match,
        number: int,
        site_team_ids: dict[int, int],
    ) -> MatchReportData:
        """What to post for *match*. The team whose player has white on
        the first board is listed on the left."""
        tournament = match.team_a.tournament
        assert tournament is not None
        team_a = match.team_a
        team_b = match.team_b
        boards = match.boards
        left, right = team_a, team_b
        if boards:
            white_team_id, _black_team_id = match.board_team_ids(boards[0])
            if white_team_id == team_b.id:
                left, right = team_b, team_a
        a_gp, b_gp = match.game_points
        if left is team_a:
            left_gp, right_gp = a_gp, b_gp
            left_mp, right_mp = match.match_points
        else:
            left_gp, right_gp = b_gp, a_gp
            right_mp, left_mp = match.match_points
        # A competition ranked on game points (Molter) has no match
        # points: the site's column stays blank rather than summing
        # points per report that the regulations do not define. The
        # site's own "Classement" then ranks nothing; the places come
        # from Sharly (see :meth:`set_team_places`).
        with_mp = match.played and tournament.primary_score != ScoreType.GAME_POINTS
        round_ = match.round
        round_datetime = tournament.round_datetimes.get(round_)
        date = (
            round_datetime.strftime('%d/%m/%Y %H:%M')
            if round_datetime
            else tournament.start_date.strftime('%d/%m/%Y')
        )
        arbiter = ''
        if chief_arbiter := tournament.chief_arbiter:
            arbiter = (
                FFEUtils.get_account_plugin_data(chief_arbiter).ffe_licence_number or ''
            )
        return MatchReportData(
            round=round_,
            number=number,
            left_team_id=site_team_ids[left.id],
            right_team_id=site_team_ids[right.id],
            left_match_points=cls._site_match_points(left_mp) if with_mp else '',
            right_match_points=cls._site_match_points(right_mp) if with_mp else '',
            left_game_points=cls._site_game_points(left_gp) if match.played else '',
            right_game_points=cls._site_game_points(right_gp) if match.played else '',
            boards=[cls._board_data(match, board, left.id) for board in boards],
            left_captain=cls._captain_licence(left),
            right_captain=cls._captain_licence(right),
            date=date,
            place=tournament.location or tournament.event.location or '',
            arbiter=arbiter,
        )

    @staticmethod
    def _site_match_points(points: float) -> str:
        # The site's match points are whole, between 0 and 3.
        value = round(points)
        if value != points or not 0 <= value <= 3:
            logger.warning(
                'Match points [%s] cannot be sent as is to the FFE website.', points
            )
        return str(min(max(value, 0), 3))

    @staticmethod
    def _site_game_points(points: float) -> str:
        # Whole and half points only, never negative (a forfeit penalty
        # can take a team below zero).
        if points < 0 or points * 2 != int(points * 2):
            logger.warning(
                'Game points [%s] cannot be sent as is to the FFE website.', points
            )
        return f'{max(round(points * 2) / 2, 0.0):.1f}'

    @classmethod
    def _captain_licence(cls, team: Team) -> str:
        captain = team.captain
        return (cls.licence_number(captain) or '') if captain else ''

    @classmethod
    def _board_data(
        cls, match: Match, board: Board, left_team_id: int
    ) -> tuple[str, str, str]:
        white_team_id, _black_team_id = match.board_team_ids(board)
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        result = board.result
        if white_team_id == left_team_id:
            left_player, right_player = white, black
        else:
            left_player, right_player = black, white
            if not result.is_bye:
                with contextlib.suppress(ValueError):
                    result = result.opposite_result
        site_result = SITE_RESULTS.get(result)
        if site_result is None:
            logger.warning(
                'Result [%s] has no equivalent on the FFE website, sent as unassigned.',
                result,
            )
            site_result = UNMAPPED_SITE_RESULT
        return (
            (cls.licence_number(left_player) or '') if left_player else '',
            (cls.licence_number(right_player) or '') if right_player else '',
            site_result,
        )

    # ---------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------

    def upload_match_reports(self) -> FailureFFEUploadStatus | None:
        """Sends the tournament to the team module: registers the teams
        that are not there yet, then fills in one match report per
        played match (existing reports are overwritten). Returns the
        failure status, None on success."""
        assert self.tournament is not None
        tournament = self.tournament
        plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
        competition_id = FFEUtils.team_competition_id(tournament)
        if (
            not plugin_data.team_configured
            or competition_id is None
            or self.upload_unavailable_message(tournament)
        ):
            return None
        assert plugin_data.team_login and plugin_data.team_password
        assert plugin_data.team_division_id and plugin_data.team_group_id

        logger.info(
            'Sending tournament [%s] to the FFE website (team module)...',
            tournament.name,
        )
        try:
            logged_in = self.login(plugin_data.team_login, plugin_data.team_password)
            if logged_in is None:
                return NotReachableFFEUploadStatus()
            if not logged_in:
                return AuthFailureFFEUploadStatus()
            try:
                page = self.open_group(
                    competition_id,
                    plugin_data.team_division_id,
                    plugin_data.team_group_id,
                )
            except SharlyChessException as error:
                logger.error(str(error))
                return GroupNotFoundFFEUploadStatus(str(error))
            if page is None:
                return NotReachableFFEUploadStatus()
            site_team_ids = self._sync_teams(page)
            page = self._sync_reports(page, site_team_ids)
            self._delete_stale_teams(page, site_team_ids)
            self.recompute_standings()
            self.set_team_places(site_team_ids)
        except SharlyChessException as error:
            logger.error('%s%s', tournament.log_prefix, error)
            return RejectedFFEUploadStatus(str(error))
        except Exception:
            logger.exception('%sUpload failed.', tournament.log_prefix)
            return UnexpectedFailureFFEUploadStatus()
        logger.info('Tournament [%s] sent to the FFE website.', tournament.name)
        return None

    @staticmethod
    def _site_team_id(page: GroupPage, team: Team) -> int | None:
        key = site_name_key(team.name[:50])
        return next(
            (
                site_id
                for name, site_id in page.teams_by_name.items()
                if site_name_key(name) == key
            ),
            None,
        )

    def _sync_teams(self, page: GroupPage) -> dict[int, int]:
        """Registers the tournament teams the group does not list under
        their name and returns the site id of every team. A renamed
        team is registered anew: its reports move to the new team and
        the old one is deleted once the reports are synced."""
        assert self.tournament is not None
        site_team_ids: dict[int, int] = {}
        missing: list[Team] = []
        for team in self.tournament.teams:
            site_id = self._site_team_id(page, team)
            if site_id is None:
                missing.append(team)
            else:
                site_team_ids[team.id] = site_id
        next_number = len(page.teams_by_name) + 1
        for team in missing:
            number = team.pairing_number or next_number
            page.teams_by_name = self.create_team(team, number).teams_by_name
            next_number = max(next_number, number) + 1
            site_id = self._site_team_id(page, team)
            if site_id is None:
                raise SharlyChessException(
                    f'Team [{team.name}] not listed after its creation.'
                )
            site_team_ids[team.id] = site_id
        return site_team_ids

    def _delete_stale_teams(
        self, page: GroupPage, site_team_ids: dict[int, int]
    ) -> None:
        """Removes the group's teams the tournament does not have; the
        site keeps those that still have reports."""
        ours = set(site_team_ids.values())
        for name, site_id in list(page.teams_by_name.items()):
            if site_id in ours:
                continue
            if self.delete_team(site_id) is None:
                logger.warning(
                    'Team [%s] is not in the tournament but could not be deleted '
                    'from the FFE website.',
                    name,
                )

    def _sync_reports(
        self, page: GroupPage, site_team_ids: dict[int, int]
    ) -> GroupPage:
        """Fills in one match report per match of every paired round,
        reusing the site's reports for the same teams and round, then
        its blank ones, and creating the rest; the group's other reports
        are deleted. Returns the group page as last read."""
        assert self.tournament is not None
        site_names = {
            site_id: site_name_key(name) for name, site_id in page.teams_by_name.items()
        }
        blanks = [report.id for report in page.match_reports if report.is_blank]
        used: set[int] = set()
        for round_ in range(1, self.tournament.last_paired_round + 1):
            for number, match in enumerate(
                self.round_matches(self.tournament, round_), start=1
            ):
                data = self.match_report_data(match, number, site_team_ids)
                names = {site_names[data.left_team_id], site_names[data.right_team_id]}
                report_id = next(
                    (
                        report.id
                        for report in page.match_reports
                        if report.id not in used
                        and report.round == round_
                        and {
                            site_name_key(report.left_team_name),
                            site_name_key(report.right_team_name),
                        }
                        == names
                    ),
                    None,
                )
                if report_id is None and blanks:
                    report_id = blanks.pop(0)
                if report_id is None:
                    report_id = self.create_blank_report(page)
                used.add(report_id)
                page = self.save_report(report_id, data)
        for report in list(page.match_reports):
            if report.id not in used:
                page = self.delete_report(report.id)
        return page
