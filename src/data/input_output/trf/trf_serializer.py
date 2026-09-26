from common.sharly_chess_config import SharlyChessConfig
from .trf_data import TrfTournament
from .trf_entry import ENTRIES, NationalPlayerEntry

import io
import re
from typing import TextIO


class TrfSerializer:
    @classmethod
    def dump(cls, fp: TextIO, tournament: TrfTournament) -> None:
        """Dumps the tournament and saves the trf in the file fp points to"""

        cls._dump_tournament(fp, tournament)

    @classmethod
    def dumps(cls, tournament: TrfTournament) -> str:
        """Dumps the tournament and returns the trf"""

        fp = io.StringIO()
        cls._dump_tournament(fp, tournament)
        return fp.getvalue()

    @classmethod
    def load(cls, fp: TextIO) -> TrfTournament:
        """Parses the trf file fp points to and returns it as a tournament"""

        return cls._parse_tournament(fp.readlines())

    @classmethod
    def loads(cls, s: str) -> TrfTournament:
        """Parses the trf in s and returns it as a tournament"""

        return cls._parse_tournament(s.split('\n'))

    @classmethod
    def _dump_tournament(cls, fp: TextIO, tournament: TrfTournament) -> None:
        for entry_ in ENTRIES:
            entry_.dump(fp, tournament)

        for federation in tournament.national_players_by_federation:
            NationalPlayerEntry(federation).dump(fp, tournament)

        for field, value in tournament.xx_fields.items():
            fp.write(f'{field} {value}\n')

        for field, value in tournament.bb_fields.items():
            fp.write(f'{field} {value}\n')

    #: A line holding round blocks only: the rest of a 001 record that an
    #: editor or a mail program wrapped.
    CONTINUATION_PATTERN = re.compile(
        r'^(?=.*\d)(  [ \d]{4} [bsw\- ] [1=0+wdl\-hfuz ])+\s*$', re.IGNORECASE
    )

    @classmethod
    def _join_wrapped_player_lines(
        cls, lines: list[str], tournament: TrfTournament
    ) -> list[str]:
        joined: list[str] = []
        for line in lines:
            if (
                joined
                and joined[-1].startswith('001 ')
                and cls.CONTINUATION_PATTERN.match(line.rstrip('\r\n'))
            ):
                joined[-1] = joined[-1].rstrip('\r\n') + line
                player_id = joined[-1][4:8].strip()
                if player_id.isdigit():
                    tournament.joined_player_lines.append(int(player_id))
                continue
            joined.append(line)
        return joined

    @classmethod
    def _parse_tournament(cls, lines: list[str]) -> TrfTournament:
        tournament = TrfTournament()
        federation_codes = [
            code
            for code in SharlyChessConfig().federations
            if code not in ('NON', 'FID')
        ]

        for line in cls._join_wrapped_player_lines(lines, tournament):
            data = line[4:].replace('\n', '')
            for entry_ in ENTRIES:
                if line.startswith(entry_.din + ' '):
                    entry_.load(tournament, data)
                    break

            din = line[:3]
            if din in federation_codes:
                NationalPlayerEntry(din).load(tournament, data)

            if line.startswith('XX'):
                field, value = line.split(' ', 1)
                tournament.xx_fields[field] = value.strip()

            elif line.startswith('BB'):
                field, value = line.split(' ', 1)
                tournament.bb_fields[field] = value.strip()

        return tournament
