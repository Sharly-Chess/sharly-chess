# Import the papi files of all the tournaments

from utils.scripts import init_script

init_script()

from common.logger import get_logger  # Noqa E402
from data.loader import EventLoader  # Noqa E402
from plugins.ffe.ffe_entity import PapiTournamentImporter  # Noqa E402


logger = get_logger()


for event in EventLoader().events_by_id.values():
    for tournament in event.tournaments:
        if not tournament.file_exists:
            logger.warning(
                tournament.log_prefix + f'File [{tournament.file}] does not exist'
            )
        elif tournament.players:
            logger.warning(tournament.log_prefix + 'Tournament already has players')
        else:
            PapiTournamentImporter().load_tournament(tournament.file, event, tournament)
            logger.info(
                tournament.log_prefix
                + f'File [{tournament.file}] successfully imported'
            )
