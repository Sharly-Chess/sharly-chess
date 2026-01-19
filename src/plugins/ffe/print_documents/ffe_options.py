from abc import ABC, abstractmethod
from types import UnionType
from typing import Any, override

from common.exception import OptionError
from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents import PrintOption
from data.print_documents.options import OptionalPlayersPrintOption
from data.tournament import Tournament
from plugins.ffe.utils import FFEUtils, PlayerFFELicence


class FFEPrintOption(PrintOption, ABC):
    @property
    def template_name(self) -> str:
        return f'/print_options/{self.template_stem}.html'

    @property
    def template_stem(self) -> str:
        """Returns the stem of the body template."""
        return self.static_id().replace('-', '_')


class FFEDocumentTypePrintOption(FFEPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-document-type'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return None

    @property
    def ffe_print_document_id(self) -> str:
        from plugins.ffe.print_documents.ffe_documents import FFEPrintDocument

        return FFEPrintDocument.static_id()

    @property
    def ffe_document_type_options(self) -> dict[str, str]:
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        return {
            ffe_document_type.static_id(): ffe_document_type.static_name()
            for ffe_document_type in FFEDocumentTypeManager().objects()
        }

    @property
    def valid_option_ids_per_type_id(self) -> dict[str, list[str]]:
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        type_options = FFEDocumentTypeManager().type_by_id()
        return {
            type_id: type_options[type_id].get_valid_option_ids()
            for type_id in type_options
        }

    @override
    def validate(self):
        super().validate()
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        if self.value not in (
            ffe_document_type.static_id()
            for ffe_document_type in FFEDocumentTypeManager().objects()
        ):
            # Untranslated, should not happen
            raise OptionError(f'Unknown FFE document type: {self.value}', self)


class FFENoLicencePlayersPrintOption(FFEPrintOption, OptionalPlayersPrintOption, ABC):
    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Returns the option ID."""

    @property
    def template_stem(self) -> str:
        return 'ffe-no-licence-players'

    @staticmethod
    @abstractmethod
    def ffe_licence() -> PlayerFFELicence:
        """Returns the FFE licence concerned."""

    @staticmethod
    @abstractmethod
    def allowed_licences() -> list[PlayerFFELicence]:
        """Returns the licences allowed for this option."""

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Returns the placeholder for this option."""

    @classmethod
    def get_tournament_players(
        cls,
        tournament: Tournament,
    ) -> list[TournamentPlayer]:
        return [
            tournament_player
            for tournament_player in tournament.tournament_players_by_name_with_unpaired
            if FFEUtils.get_player_plugin_data(tournament_player).ffe_licence
            not in cls.allowed_licences()
        ]

    @classmethod
    def get_players_per_tournament(
        cls,
        tournaments: list[Tournament],
    ) -> dict[int, list[dict[str, Any]]]:
        return {
            tournament.id: [
                {
                    'id': tournament_player.id,
                    'full_name': tournament_player.full_name,
                }
                for tournament_player in cls.get_tournament_players(tournament)
            ]
            for tournament in tournaments
        }


class FFET3NoLicencePlayersPrintOption(FFENoLicencePlayersPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t3-no-licence-players'

    @staticmethod
    def ffe_licence() -> PlayerFFELicence:
        return PlayerFFELicence.A

    @staticmethod
    def allowed_licences() -> list[PlayerFFELicence]:
        return [
            PlayerFFELicence.A,
        ]

    @property
    def placeholder(self) -> str:
        return _('All the players with no FFE licence A')


class FFET4NoLicencePlayersPrintOption(FFENoLicencePlayersPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t4-no-licence-players'

    @staticmethod
    def ffe_licence() -> PlayerFFELicence:
        return PlayerFFELicence.B

    @staticmethod
    def allowed_licences() -> list[PlayerFFELicence]:
        return [
            PlayerFFELicence.A,
            PlayerFFELicence.B,
        ]

    @property
    def placeholder(self) -> str:
        return _('All the players with no FFE licence A/B')
