from functools import partial
from logging import Logger
import time
import uuid
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from dotenv import load_dotenv
import os

import requests
from requests import Session

from common.i18n import _
from common.logger import get_logger
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.chess_results_mappers import (
    ChessResultsPlayerGender,
    ChessResultsTieBreak,
)
from plugins.chess_results.utils import ChessResultsUtils
from plugins.utils import PluginUtils
from utils.enum import Result

load_dotenv()
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

    @staticmethod
    def get_bytes_from_env(var_name: str) -> bytes:
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f'Missing environment variable: {var_name}')
        return bytes.fromhex(value)

    def encrypt(self, decrypted_string: str) -> str:
        """
        Returns a HEX-encoded encrypted string (uppercase).
        """
        key = self.get_bytes_from_env('CHESS_RESULTS_AES_KEY')
        iv = self.get_bytes_from_env('CHESS_RESULTS_AES_IV')

        data = decrypted_string.encode('utf-8')

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
        return encrypted_bytes.hex().upper()

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
                    sid="{self.encrypt(sid)}"
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
        self, tournament: Tournament, sid: str, tnr: str, creator_id: str
    ) -> str:
        """
        Build Chess-Results upload XML from a Sharly Chess Rournament.
        """

        root = ET.Element('chessresults')

        # --- Tournament section ---
        tdata = ET.SubElement(root, 'tournamentdata')

        # Get up to 5 tiebreak keys (pad with zeros if fewer)
        tb_details: list[tuple[str, str]] = []
        for tb in tournament.tie_breaks[:5]:
            tb_data = ChessResultsTieBreak.data_for_tiebreak(tb)
            if tb_data:
                params_str = ','.join(v for v in tb_data[1:] if v)
                tb_details.append((tb_data[0], params_str))
            else:
                tb_details.append(('0', ''))
        while len(tb_details) < 5:
            tb_details.append(('0', ''))

        ET.SubElement(
            tdata,
            'tournament',
            {
                'key': str(tnr),
                'type': '0',  # 0=Swiss, 1=Round robin, etc.
                'name': tournament.full_name,
                'fideeventid': '',
                'remark': f'#{ChessResultsUtils.resolve_remark(tournament)}',
                'director': '',
                'organiser': '',
                'location': tournament.location or '',
                'arbiter': '     ',
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
                'from': tournament.start_datetime.strftime('%Y%m%d'),
                'to': tournament.stop_datetime.strftime('%Y%m%d'),
                'ratedfide': '-',
                'ratednational': '-',
                'tb1no': tb_details[0][0],
                'tb2no': tb_details[1][0],
                'tb3no': tb_details[2][0],
                'tb4no': tb_details[3][0],
                'tb5no': tb_details[4][0],
                'replay': '1',
                'timecontrol': tournament.time_control_trf25 or '',
                'homecolor': '',
                'samecolor': '',
                'playerperteam': '',
                'category': '0',
                'ratingavg': str(round(tournament.average_player_rating)),
                'endstatus': 'N',
                'tb1_detail': tb_details[0][1],
                'tb2_detail': tb_details[1][1],
                'tb3_detail': tb_details[2][1],
                'tb4_detail': tb_details[3][1],
                'tb5_detail': tb_details[4][1],
                'chiefarbiter': '',
                'deputyarbiter': '',
                'homepageorganiser': '',
                'mail': '',
                'federation': tournament.event.federation or 'FID',
                'creator': creator_id,
            },
        )

        # --- Rounds section ---
        rdata = ET.SubElement(root, 'rounds')
        for rnd in range(1, tournament.rounds + 1):
            ET.SubElement(
                rdata,
                'round',
                {
                    'round': str(rnd),
                    'date': '',
                    'time': '',
                },
            )

        # --- Player list ---
        pdata = ET.SubElement(root, 'players')
        prev_tb_values: list[str] | None = None

        for p in tournament.players_by_pairing_number.values():
            # Get up to 5 tiebreak keys (pad with zeros if fewer)
            tb_values: list[str] = []
            for tbv in p.tie_break_values[:5]:
                value = str(tbv.value)
                tb_values.append(str(value))
            while len(tb_values) < 5:
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
                    'typ': p.category.short_name,
                    'rank': str(p.rank),
                    'pts': str(p.points or 0),
                    'tb1': tb_values[0],
                    'tb2': tb_values[1],
                    'tb3': tb_values[2],
                    'tb4': tb_values[3],
                    'tb5': tb_values[4],
                    'equal': 'J' if same_as_previous else 'N',
                    'kfaktor': '',
                    'state': '',
                },
            )

        # --- Pairings / Results ---
        ppair = ET.SubElement(root, 'playerpairings')
        for round_ in range(1, tournament.current_round + 1):
            tournament.set_for_round(round_)
            tournament.compute_player_ranks(after_round=round_)
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
                        'whiteno': str(board.white_player.pairing_number),
                        'blackno': str(
                            board.black_player.pairing_number
                            if board.black_player
                            else -1
                        ),
                        'reswhite': str(
                            board.white_pairing.result.points(tournament.point_values)
                            or ''
                        ),
                        'resblack': str(
                            board.black_pairing.result.points(tournament.point_values)
                            or ''
                        )
                        if board.black_player
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

            for player in tournament.get_unpaired_players(boards):
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
                        'reswhite': str(result.points(tournament.point_values) or ''),
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
                'sid': self.encrypt(sid),
                'creator_sid': self.encrypt(creator_id),
                'tnr_sid': self.encrypt(str(tnr)),
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
            self.tournament.uniq_id,
        )

        sid = self._chess_results_init()
        plugin_data = ChessResultsUtils.get_tournament_plugin_data(self.tournament)
        tnr = plugin_data.tnr
        creator_id = plugin_data.creator_id
        if not tnr:
            # First upload, create the tournament on the site
            creator_id = str(uuid.uuid4())
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
        xml_data = self.build_tournament_xml(self.tournament, sid, tnr, creator_id)
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
                now = time.time()
                event_database.execute(
                    """
                    UPDATE tournament
                    SET plugin_data = json_set(
                            plugin_data,
                            '$.chess_results.last_upload', ?
                        ),
                        last_update = ?
                    WHERE id = ?
                    """,
                    (now, now, self.tournament.id),
                )

            self.report_success(_('Results upload OK'))
            return

        msg = root.find('.//message')

        if msg is not None:
            error_text = msg.attrib.get('Text', '')
            if 'MsgNo:28' in error_text:
                self.report_error(_('Tournament finished, upload no longer possible.'))
            else:
                self.report_error(error_text)
        else:
            self.report_error(_('Unknown error when uploading results.'))
