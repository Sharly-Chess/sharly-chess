import re
import types
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Pattern, Iterator

from common.logger import get_logger
from database.access.access_database import AccessDatabase

logger: Logger = get_logger()


class FfeAccessDatabase(AccessDatabase):
    """The FFE database class, downloaded from the FFE site and used to fill the FFE local database."""

    def __init__(self, file: Path, write: bool = False):
        super().__init__(file, write)
        self.date_of_birth_pattern: Pattern = re.compile(r'^\d{1,2}/\d{1,2}/(\d{1,4})$')

    def read_player_dicts(self) -> Iterator[dict[str, str | int | datetime | None]]:
        # the fields common to players with a club or not
        common_fields: dict[str, tuple[str, types.FunctionType]] = {
            'ffe_id': 'joueur.Ref',  # int
            'ffe_licence_number': 'joueur.NrFFE',  # str
            'last_name': 'joueur.Nom',  # str
            'first_name': 'joueur.Prenom',  # str
            'gender': 'joueur.Sexe',  # str
            'date_of_birth': 'joueur.NeLe',  # datetime
            'federation': 'joueur.Federation',  # str
            'standard_rating': 'joueur.Elo',  # int
            'rapid_rating': 'joueur.Rapide',  # int
            'blitz_rating': 'joueur.Blitz',  # int
            'standard_rating_type': 'joueur.Fide',  # str
            'rapid_rating_type': 'joueur.RapideFide',  # str
            'blitz_rating_type': 'joueur.BlitzFide',  # str
            'fide_id': 'joueur.FideCode',  # int
            'fide_title': 'joueur.FideTitre',  # str
            'ffe_licence': 'joueur.AffType',  # str
        }
        # the fields for players with a club
        club_fields: dict[str, tuple[str, types.FunctionType]] = common_fields | {
            # '': 'club.NrFFE',
            'club': 'club.Nom',  # str
            'league': 'club.Ligue',  # str
            'city': 'club.Commune',  # str
        }
        # the fields for players with a club
        no_club_fields: dict[str, tuple[str, types.FunctionType]] = common_fields | {
            'club': '\'\'',  # str
            'league': '\'\'',  # str
            'city': '\'\'',  # str
        }
        club_query_fields = (
            f'{field_name} AS {field_as}' for field_as, field_name in club_fields.items()
        )
        club_query: str = f'SELECT {", ".join(club_query_fields)} FROM joueur INNER JOIN club ON joueur.ClubRef = club.Ref'
        no_club_query_fields = (
            f'{field_name} AS {field_as}' for field_as, field_name in no_club_fields.items()
        )
        no_club_query: str = f'SELECT {", ".join(no_club_query_fields)} FROM joueur WHERE ClubRef = 0'
        self._execute(f'({club_query}) UNION ({no_club_query})')
        return self._fetchall()
