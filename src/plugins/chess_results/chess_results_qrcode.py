from common.i18n import _
from data.print_documents import QRCodeType
from data.print_documents.documents import QRCodePrintDocument
from data.print_documents.options import TournamentPrintOption, PrintOption
from plugins.chess_results import PLUGIN_NAME, PLUGIN_DIR
from plugins.chess_results.utils import CRUtils


class ChessResultsQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-cr_site'

    @staticmethod
    def static_name() -> str:
        return _('Tournament on Chess-results.com')

    @staticmethod
    def get_valid_option_types() -> list[type[PrintOption]]:
        return [TournamentPrintOption]

    @staticmethod
    def title(doc: QRCodePrintDocument) -> str:
        tournament = doc.tournament
        return tournament.name

    @staticmethod
    def info(doc: QRCodePrintDocument) -> str:
        return _('Scan to access the tournament on Chess-Results.com.')

    @staticmethod
    def url(doc: QRCodePrintDocument) -> tuple[bool, str]:
        tournament = doc.tournament
        tnr = CRUtils.get_tournament_plugin_data(tournament).tnr

        if not tnr:
            return False, _(
                'No Chess-Results ID defined for tournament [{tournament}].'
            ).format(tournament=tournament.name)
        url = f'https://chess-results.com/tnr{tnr}.aspx'
        return True, url

    @staticmethod
    def get_qr_code(url) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=PLUGIN_DIR / 'static' / 'images' / 'chess-results-qr-logo.jpg',
        )
