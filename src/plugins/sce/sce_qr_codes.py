from common.i18n import _
from data.print_documents import QRCodeType
from data.print_documents.documents import QRCodePrintDocument
from data.print_documents.options import TournamentPrintOption, PrintOption
from plugins.sce import PLUGIN_NAME, PLUGIN_DIR
from plugins.sce.utils import SCEUtils


class SCEEventQRCodeType(QRCodeType):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        return []

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-sce-event'

    @staticmethod
    def static_name() -> str:
        return _('Event on Sharly-Chess.com')

    @staticmethod
    def title(doc: QRCodePrintDocument) -> str:
        assert doc.event is not None
        return doc.event.name

    @staticmethod
    def info(doc: QRCodePrintDocument) -> str:
        return _('Scan to access the event on Sharly-Chess.com.')

    @staticmethod
    def url(doc: QRCodePrintDocument) -> tuple[bool, str]:
        event = doc.event
        assert event is not None
        if not SCEUtils.get_event_plugin_data(event).id:
            return False, _(
                'Event [{event}] is not connected to a Sharly-Chess.com event.'
            ).format(event=event.name)
        return True, SCEUtils.event_public_url(event)

    @staticmethod
    def get_qr_code(url) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=PLUGIN_DIR / 'static' / 'images' / 'sce-qr-logo.jpg',
        )


class SCETournamentQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-sce-tournament'

    @staticmethod
    def static_name() -> str:
        return _('Tournament on Sharly-Chess.com')

    @staticmethod
    def get_valid_option_types() -> list[type[PrintOption]]:
        return [TournamentPrintOption]

    @staticmethod
    def title(doc: QRCodePrintDocument) -> str:
        tournament = doc.tournament
        return tournament.name

    @staticmethod
    def info(doc: QRCodePrintDocument) -> str:
        return _('Scan to access the tournament on Sharly-Chess.com.')

    @staticmethod
    def url(doc: QRCodePrintDocument) -> tuple[bool, str]:
        tournament = doc.tournament
        if not SCEUtils.get_tournament_plugin_data(tournament).id:
            return False, _(
                'Tournament [{tournament}] is not '
                'connected to a Sharly-Chess.com tournament.'
            ).format(tournament=tournament.name)
        return True, SCEUtils.tournament_public_url(tournament)

    @staticmethod
    def get_qr_code(url) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=PLUGIN_DIR / 'static' / 'images' / 'sce-qr-logo.jpg',
        )
