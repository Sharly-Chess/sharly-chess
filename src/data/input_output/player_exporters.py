import csv
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import xlsxwriter
from litestar import Response
from litestar.response import File
from pyexcel_ods3 import save_data

from common.i18n import _
from data.columns.handlers import PlayerDatasheetColumnHandler
from data.event import Event
from data.player import Player
from utils.entity import IdentifiableEntity


class PlayerExporter(IdentifiableEntity, ABC):
    @property
    def warning_tooltip(self) -> str:
        """tooltip to display as a warning on the exporter option."""
        return ''

    @abstractmethod
    def download_players_file(
        self, players: list[Player], event: Event
    ) -> Response[str] | File:
        """Download a file containing the players in the format of the exporter."""


class PlayerTabularExporter(PlayerExporter):
    @abstractmethod
    def _get_tabular_file_path(self, header: list[str], data: list[list[Any]]) -> Path:
        """Convert the header and data into a file and return its path."""

    @property
    def suffix(self) -> str:
        return f'.{self.id}'

    def download_players_file(
        self, players: list[Player], event: Event
    ) -> Response[str] | File:
        columns = PlayerDatasheetColumnHandler(event).export_columns
        header = [column.id for column in columns]
        data = [
            [column.get_cell_content(player) for column in columns]
            for player in players
        ]
        file_path = self._get_tabular_file_path(header, data)
        return File(path=file_path, filename=f'{event.uniq_id}{self.suffix}')


class VcfPlayerExporter(PlayerExporter):
    @staticmethod
    def static_id() -> str:
        return 'vcf'

    @staticmethod
    def static_name() -> str:
        return _('Contact (vCards)')

    @property
    def warning_tooltip(self) -> str:
        return _("Players without phone or email won't be included.")

    def download_players_file(
        self, players: list[Player], event: Event
    ) -> Response[str] | File:
        data: str = ''
        for player in players:
            if not (player.mail or player.phone):
                continue
            data += 'BEGIN:VCARD\nVERSION:3.0\n'
            if player.first_name:
                data += (
                    f'N:{player.last_name.title()};{player.first_name}\n'
                    f'FN:{player.first_name} {player.last_name.title()}\n'
                )
            else:
                data += f'N:{player.last_name.title()}\nFN:{player.last_name.title()}\n'
            data += (
                f'ORG:{player.club}\n'
                f'item1.TEL:{player.phone or ""}\n'
                f'item1.X-ABLabel:{_("Personal")}\n'
                f'item2.EMAIL;type=INTERNET:{player.mail or ""}\n'
                f'item2.X-ABLabel:{_("Personal")}\n'
                f'CATEGORIES:{_("Chess")}\n'
                'END:VCARD\n\n'
            )
        return Response(
            content=data,
            media_type='text/x-vcard',
            headers={
                'Content-Disposition': f'attachment;{event.uniq_id}.vcf',
            },
        )


class XlsxPlayerExporter(PlayerTabularExporter):
    @staticmethod
    def static_id() -> str:
        return 'xlsx'

    @staticmethod
    def static_name() -> str:
        return _('XLSX format')

    def _get_tabular_file_path(self, header: list[str], data: list[list[Any]]) -> Path:
        temp_file = NamedTemporaryFile(delete=False, mode='wb', suffix='.xlsx')
        workbook = xlsxwriter.Workbook(temp_file)
        worksheet = workbook.add_worksheet()
        worksheet.add_table(
            0,
            0,
            len(data),
            len(header) - 1,
            options={
                'columns': [{'header': header} for header in header],
                'data': data,
            },
        )
        worksheet.autofit()
        workbook.close()
        return Path(temp_file.name)


class CsvPlayerExporter(PlayerTabularExporter):
    @staticmethod
    def static_id() -> str:
        return 'csv'

    @staticmethod
    def static_name() -> str:
        return _('CSV format')

    def _get_tabular_file_path(self, header: list[str], data: list[list[Any]]) -> Path:
        temp_file = NamedTemporaryFile(
            delete=False, mode='w', suffix='.csv', newline=''
        )
        writer = csv.writer(temp_file)
        writer.writerow(header)
        writer.writerows(data)
        return Path(temp_file.name)


class OdsPlayerExporter(PlayerTabularExporter):
    @staticmethod
    def static_id() -> str:
        return 'ods'

    @staticmethod
    def static_name() -> str:
        return _('ODS format')

    def _get_tabular_file_path(self, header: list[str], data: list[list[Any]]) -> Path:
        temp_file = NamedTemporaryFile(delete=False, mode='w+b', suffix='.ods')
        save_data(temp_file, [header] + data)
        return Path(temp_file.name)
