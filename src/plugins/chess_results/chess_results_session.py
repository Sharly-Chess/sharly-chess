import random
import xml.etree.ElementTree as ET
from functools import partial
from logging import Logger

import requests
from requests import Session

from common.i18n import _
from common.logger import get_logger
from data.tournament import Tournament
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.chess_results import PLUGIN_NAME, MAX_TIE_BREAKS
from plugins.chess_results.chess_results_mappers import (
    ChessResultTournamentRating,
    ChessResultsPlayerGender,
    ChessResultsTieBreak,
    ChessResultPairingSystem,
)
from plugins.chess_results.utils import ChessResultsUtils
from plugins.manager import plugin_manager
from plugins.utils import PluginUtils
from utils.enum import Result
from utils.time_control import trf25_to_human_readable

logger: Logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

CHESS_RESULTS_URL: str = 'https://chess-results.com/Uploadxml.aspx'
CHESS_RESULTS_SOURCE = 13


class ChessResultsSession(Session):
    """A requests session specialized for communication with Chess-Results.com."""

    def __init__(
        self,
        tournament: Tournament | None,
        report_info=logger.info,
        report_success=logger.info,
        report_error=logger.error,
    ):
        super().__init__()
        self.tournament: Tournament | None = tournament
        self.report_info = report_info
        self.report_success = report_success
        self.report_error = report_error

    def _chess_results_init(self) -> str:
        """Initializes a session on Chess-Results.com
        Return sid on success, False otherwise."""
        url = CHESS_RESULTS_URL
        params = {'key1': 'GETSID', 'source': CHESS_RESULTS_SOURCE}

        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an error if the request failed
        root = ET.fromstring(response.text)

        result = root.find('result')
        if result is not None and result.attrib.get('status') == 'OK':
            return result.attrib['sid']

        raise Exception('No SID found in response.')

    def get_new_tournament_key(
        self, source: int, sid: str, creator_id: str, tournament: Tournament
    ) -> str:
        url = 'https://chess-results.com/Uploadxml.aspx'
        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
            <chessresults>
                <getkey
                    source="{source}"
                    sid="{ChessResultsUtils.encrypt(sid)}"
                    creatorID="{creator_id}"
                    federation="{tournament.event.federation}"
                    tournament="{tournament.full_name}" />
            </chessresults>"""

        headers = {'Content-Type': 'application/xml'}
        resp = requests.post(
            url,
            params={'key1': 'GETKEY'},
            data=xml_payload.encode('utf-8'),
            headers=headers,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        result = root.find('result')
        if result is not None and result.attrib.get('status') == 'OK':
            return result.attrib['key']
        else:
            raise RuntimeError('GETKEY failed: ' + resp.text)

    def build_tournament_xml(
        self,
        tournament: Tournament,
        sid: str,
        tnr: str,
        creator_id: str,
        state: int | None,
    ) -> str:
        """
        Build Chess-Results upload XML from a Sharly Chess Tournament.
        """

        event = tournament.event
        root = ET.Element('chessresults')

        # --- Tournament section ---
        tdata = ET.SubElement(root, 'tournamentdata')

        # Get up to `MAX_TIE_BREAKS`` tiebreak keys (pad with zeros if fewer)
        tb_details: list[tuple[str, str]] = []
        for tie_break in tournament.tie_breaks[:MAX_TIE_BREAKS]:
            cr_tie_break = ChessResultsTieBreak.from_tie_break(tournament, tie_break)
            tb_details.append((str(cr_tie_break.number), cr_tie_break.params_str))
        while len(tb_details) < MAX_TIE_BREAKS:
            tb_details.append(('0', ''))

        ET.SubElement(
            tdata,
            'tournament',
            {
                'key': str(tnr),
                'type': ChessResultPairingSystem.get_outer_value(
                    tournament.pairing_system
                )
                or '',
                'name': tournament.full_name[:160],
                'fideeventid': '',
                'remark': f'#{ChessResultsUtils.resolve_remark(tournament)}'[:599],
                'director': (event.organiser_director or '')[:80],
                'organiser': (event.organiser_name or '')[:80],
                'location': tournament.location or '',
                'rounds': str(tournament.rounds),
                'currentround': str(tournament.current_round or 0),
                'rankinground': str(
                    max(
                        0,
                        tournament.current_round - 1
                        if tournament.playing
                        else tournament.current_round,
                    )
                ),
                'sortstartrank': '2',
                'from': tournament.start_date.strftime('%Y%m%d'),
                'to': tournament.stop_date.strftime('%Y%m%d'),
                'ratedfide': '-',
                'ratednational': '-',
                'replay': '1',
                'timetype': ChessResultTournamentRating.get_outer_value(
                    tournament.rating
                )
                or '',
                'timecontrol': trf25_to_human_readable(tournament.time_control_trf25)
                if tournament.time_control_trf25
                else '',
                'homecolor': '',
                'samecolor': '',
                'playerperteam': '',
                'ratingavg': str(round(tournament.average_player_rating)),
                'endstatus': 'N',
                'chiefarbiter': getattr(
                    tournament.chief_arbiter, 'fide_arbiter_str', ''
                ),
                'deputyarbiter': ', '.join(
                    arbiter.fide_arbiter_str for arbiter in tournament.deputy_arbiters
                ),
                'homepageorganiser': (event.organiser_home_page or '')[:80],
                'mail': (event.organiser_email or '')[:80],
                'federation': tournament.event.federation or 'FID',
                'federalstate': str(state) if state else '',
                'creator': creator_id,
            }
            | {f'tb{i + 1}no': tb_details[i][0] for i in range(MAX_TIE_BREAKS)}
            | {
                f'tb{i + 1}_detail': tb_details[i][1]
                for i in range(min(MAX_TIE_BREAKS, len(tb_details)))
            },
        )

        # --- Rounds section ---
        rdata = ET.SubElement(root, 'rounds')
        for rnd in range(1, tournament.rounds + 1):
            dt = tournament.round_datetimes.get(rnd)
            ET.SubElement(
                rdata,
                'round',
                {
                    'round': str(rnd),
                    'date': dt.strftime('%Y/%m/%d') if dt else '',
                    'time': dt.strftime('%H:%M') if dt else '',
                },
            )

        # --- Player list ---
        pdata = ET.SubElement(root, 'players')
        prev_tb_values: list[str] | None = None

        for p in tournament.tournament_players_by_pairing_number.values():
            # Get up to `MAX_TIE_BREAKS` tiebreak keys (pad with zeros if fewer)
            tb_values: list[str] = []
            for tbv in p.tie_break_values[:MAX_TIE_BREAKS]:
                value = str(tbv.value)
                if tbv.tie_break.is_manual:
                    value = str(1000 - float(tbv.value))
                tb_values.append(str(value))
            while len(tb_values) < MAX_TIE_BREAKS:
                tb_values.append('')

            same_as_previous = (
                tb_values == prev_tb_values if prev_tb_values is not None else False
            )
            prev_tb_values = tb_values

            ratings = p.ratings.get(tournament.rating)
            ET.SubElement(
                pdata,
                'player',
                {
                    'no': str(
                        p.pairing_number if p.pairing_number is not None else p.rank
                    ),
                    'id': str(p.id),
                    'lastname': p.last_name,
                    'firstname': p.first_name or '',
                    'atitle': '',
                    'title': p.title.short_name,
                    'rtg': str(p.rating),
                    'rtgfide': str(getattr(ratings, 'fide', '') or ''),
                    'rtgnat': str(getattr(ratings, 'national', '') or ''),
                    'dob': str(p.year_of_birth),
                    'sex': ChessResultsPlayerGender.get_outer_value(p.gender) or '',
                    'fed': p.federation.name,
                    'board': '',
                    'teamno': '0',
                    'fideid': str(p.fide_id or ''),
                    'clubname': p.club.name or '',
                    'typ': p.category.name,
                    'rank': str(p.rank),
                    'pts': str(p.points or 0),
                    'equal': 'J' if same_as_previous else 'N',
                    'kfaktor': '',
                    'state': '',
                }
                | {f'tb{i + 1}': tb_values[i] for i in range(MAX_TIE_BREAKS)},
            )

        # --- Pairings / Results ---
        ppair = ET.SubElement(root, 'playerpairings')
        point_values: dict[Result, float] = {
            Result.PAIRING_ALLOCATED_BYE: tournament.pab_value.point_value,
        }
        for round_ in range(1, tournament.current_round + 1):
            tournament.set_for_round(round_)
            tournament.compute_tournament_player_ranks(after_round=round_)
            last_board_id = 0
            boards = tournament.get_round_boards(round_)
            for board in boards:
                ET.SubElement(
                    ppair,
                    'playerpairing',
                    {
                        'round': str(round_),
                        'pairing': str(board.board_id),
                        'board': '1',
                        'whiteno': str(board.white_tournament_player.pairing_number),
                        'blackno': str(
                            board.black_tournament_player.pairing_number
                            if board.black_tournament_player
                            else -1
                        ),
                        'reswhite': str(
                            board.white_pairing.result.points(point_values) or ''
                        ),
                        'resblack': str(
                            board.black_pairing.result.points(point_values) or ''
                        )
                        if board.black_tournament_player
                        else '',
                        'forfeit': 'K'
                        if board.result
                        in [
                            Result.FORFEIT_LOSS,
                            Result.FORFEIT_WIN,
                            Result.DOUBLE_FORFEIT,
                            Result.PENALTY_LL,
                            Result.UNRATED_PENALTY_LL,
                        ]
                        else '',
                    },
                )
                last_board_id = board.board_id

            for player in tournament.get_unpaired_tournament_players(boards):
                last_board_id += 1
                result = player.pairings_by_round[round_].result
                ET.SubElement(
                    ppair,
                    'playerpairing',
                    {
                        'round': str(round_),
                        'pairing': str(last_board_id),
                        'board': '1',
                        'whiteno': str(player.pairing_number),
                        'blackno': '-2',
                        'reswhite': str(result.points(point_values) or ''),
                        'resblack': '',
                        'forfeit': '',
                    },
                )

        # --- Security section ---
        security = ET.SubElement(root, 'security')
        ET.SubElement(
            security,
            'securitydata',
            {
                'source': str(CHESS_RESULTS_SOURCE),
                'sid': ChessResultsUtils.encrypt(sid),
                'creator_sid': ChessResultsUtils.encrypt(creator_id),
                'tnr_sid': ChessResultsUtils.encrypt(str(tnr)),
            },
        )

        # Return as UTF-8 XML
        xml_bytes = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        return xml_bytes.decode('utf-8')

    def upload(self):
        """Upload the tournament to Chess-Results.com."""

        assert self.tournament is not None
        logger.info(
            'Sending tournament (%s) to Chess-Results.com...',
            self.tournament.name,
        )

        sid = self._chess_results_init()
        tournament_plugin_data = ChessResultsUtils.get_tournament_plugin_data(
            self.tournament
        )
        event_plugin_data = ChessResultsUtils.get_event_plugin_data(
            self.tournament.event
        )
        tnr = tournament_plugin_data.tnr
        creator_id = tournament_plugin_data.creator_id

        if not tnr:
            # See if we have a creator_id stored in the config
            chess_results_plugin = plugin_manager.plugins_by_id[PLUGIN_NAME]
            chess_results_plugin_data = chess_results_plugin.get_plugin_data()
            creator_id = chess_results_plugin_data.creator_id
            if not creator_id:
                creator_id = str(random.randint(1, 2**16 - 1))
                with ConfigDatabase(write=True) as config_database:
                    chess_results_plugin_data.creator_id = creator_id
                    stored_plugin = chess_results_plugin.context.stored_plugin
                    stored_plugin.plugin_data = (
                        chess_results_plugin_data.to_stored_value()
                    )
                    config_database.update_stored_plugin(stored_plugin)

            # First upload, create the tournament on the site
            tnr = self.get_new_tournament_key(13, sid, creator_id, self.tournament)

            with EventDatabase(
                self.tournament.event.uniq_id, write=True, check_dirty_tournaments=False
            ) as event_database:
                event_database.execute(
                    """
                    UPDATE tournament
                    SET plugin_data = json_set(
                            plugin_data,
                            '$.chess_results.tnr', ?,
                            '$.chess_results.creator_id', ?
                        )
                    WHERE id = ?
                    """,
                    (
                        tnr,
                        creator_id,
                        self.tournament.id,
                    ),
                )

        assert creator_id is not None
        xml_data = self.build_tournament_xml(
            self.tournament, sid, tnr, creator_id, event_plugin_data.state
        )
        logger.debug(xml_data)

        xml_sanitized = xml_data.replace('<', '{').replace('>', '}')
        url = f'{CHESS_RESULTS_URL}?key1=UPLOAD'
        response = requests.post(url, data={'xml': xml_sanitized})
        response.raise_for_status()

        root = ET.fromstring(response.text)
        result = root.find('result')
        logger.debug(response.text)
        if result is not None and result.attrib.get('status') == 'OK':
            with EventDatabase(
                self.tournament.event.uniq_id, write=True, check_dirty_tournaments=False
            ) as event_database:
                # NOTE (Molrn) Bypass standard DB write to avoid updating
                # the last_update flag which would re-trigger an upload
                now = SQLiteDatabase.now_as_database_timestamp()
                event_database.execute(
                    """
                    UPDATE tournament SET plugin_data = json_set(
                        plugin_data, '$.chess_results.last_upload', ?
                    ) WHERE id = ?
                    """,
                    (now, self.tournament.id),
                )

            self.report_success(_('Results upload OK'))
            return

        msg = root.find('.//message')

        if msg is not None:
            error_text = msg.attrib.get('Text', '')
            if 'MsgNo:28' in error_text:
                self.report_error(_('Tournament finished, upload no longer possible.'))
                return

            # Retry logic: Invalid Source-ID or tournament number
            # This can happen if the user deletes the tournament and then tries to upload again
            if 'Source-ID (Swiss-Manager Tournaments) not valid' in error_text:
                logger.warning(
                    'Invalid Source-ID detected, retrying without tnr/creator_id...'
                )

                # Remove the invalid keys
                with EventDatabase(
                    self.tournament.event.uniq_id,
                    write=True,
                    check_dirty_tournaments=False,
                ) as event_database:
                    event_database.execute(
                        """
                        UPDATE tournament
                        SET plugin_data = json_remove(
                                plugin_data,
                                '$.chess_results.tnr',
                                '$.chess_results.creator_id'
                            )
                        WHERE id = ?
                        """,
                        (self.tournament.id,),
                    )

                # Clear in-memory values too
                tournament_plugin_data.tnr = None
                tournament_plugin_data.creator_id = None
                self.tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
                    tournament_plugin_data.to_stored_value()
                )

                # Retry the upload once (fresh creation)
                self.upload()
                return

            self.report_error(error_text)
        else:
            self.report_error(_('Unknown error when uploading results.'))
