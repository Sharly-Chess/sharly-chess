from pathlib import Path
from typing import IO

from common.i18n import _
from data.input_output import TournamentExporter
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.papi_converter import PapiConverter
from utils.enum import EventType


class PapiTournamentExporter(TournamentExporter):
    # Papi is an individual-tournament format. Team events are offered it
    # too so that a Scheveningen — which flattens to an individual Swiss —
    # can be exported; the other team tournaments are disabled per-tournament
    # by is_unavailable_message.
    supported_event_types = [EventType.INDIVIDUAL, EventType.TEAM]

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-papi'

    @staticmethod
    def static_name() -> str:
        return _('PAPI')

    def is_unavailable_message(self, tournament: Tournament) -> str | None:
        return PapiConverter.papi_export_unavailable_message(tournament)

    def warning_message(self, tournament: Tournament) -> str | None:
        return PapiConverter.papi_export_warning(tournament)

    @property
    def file_extension(self) -> str:
        return 'papi'

    def dump_to_file(self, file: IO, tournament: Tournament):
        file.close()
        PapiConverter().write_papi_file(tournament, Path(file.name))
