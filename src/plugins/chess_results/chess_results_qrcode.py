from common import BASE_DIR
from common.i18n import _
from data.print_documents import QRCodeType
from data.print_documents.documents import QRCodePrintDocument
from data.print_documents.options import TournamentPrintOption
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.utils import ChessResultsUtils


class ChessResultsQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_site'

    @staticmethod
    def static_name() -> str:
        return _('Tournament on Chess-results.com')

    @staticmethod
    def get_valid_options() -> list[str]:
        return [TournamentPrintOption.static_id()]

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
        tnr = ChessResultsUtils.get_tournament_plugin_data(tournament).tnr

        if not tnr:
            return False, _(
                'No Chess-Results ID defined for tournament [{tournament}].'
            ).format(tournament=tournament.uniq_id)
        url = f'https://s3.chess-results.com/tnr{tnr}.aspx'
        return True, url

    @staticmethod
    def get_qr_code(url) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=BASE_DIR
            / 'src'
            / 'web'
            / 'static'
            / 'images'
            / 'chess-results-qr-logo.jpg',
        )
