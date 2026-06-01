from common.sharly_chess_config import SharlyChessConfig
from .trf_data import TrfTournament
from .trf_entry import ENTRIES, NationalPlayerEntry

import io


class TrfSerializer:
    @classmethod
    def dump(cls, fp, tournament: TrfTournament):
        """Dumps the tournament and saves the trf in the file fp points to"""

        cls._dump_tournament(fp, tournament)

    @classmethod
    def dumps(cls, tournament: TrfTournament) -> str:
        """Dumps the tournament and returns the trf"""

        fp = io.StringIO()
        cls._dump_tournament(fp, tournament)
        return fp.getvalue()

    @classmethod
    def load(cls, fp) -> TrfTournament:
        """Parses the trf file fp points to and returns it as a tournament"""

        return cls._parse_tournament(fp.readlines())

    @classmethod
    def loads(cls, s: str) -> TrfTournament:
        """Parses the trf in s and returns it as a tournament"""

        return cls._parse_tournament(s.split('\n'))

    @classmethod
    def _dump_tournament(cls, fp, tournament):
        for entry_ in ENTRIES:
            entry_.dump(fp, tournament)

        for (
            federation,
            national_players,
        ) in tournament.national_players_by_federation.items():
            NationalPlayerEntry(federation).dump(fp, tournament)

        for field, value in tournament.xx_fields.items():
            fp.write(f'{field} {value}\n')

        for field, value in tournament.bb_fields.items():
            fp.write(f'{field} {value}\n')

    @classmethod
    def _parse_tournament(cls, lines):
        tournament = TrfTournament()
        federation_codes = [
            code
            for code in SharlyChessConfig().federations
            if code not in ('NON', 'FID')
        ]

        for line in lines:
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
