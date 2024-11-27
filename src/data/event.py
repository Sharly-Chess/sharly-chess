import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import total_ordering, cached_property
from logging import Logger
from operator import attrgetter
from pathlib import Path

from common import format_timestamp_date_time, format_timestamp_date, format_timestamp_time
from common.background import inline_image_url
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.chessevent import ChessEvent
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from data.screen_set import ScreenSet
from data.timer import Timer, TimerHour
from data.tournament import Tournament
from data.util import ScreenType
from database.store import StoredEvent

logger: Logger = get_logger()

event_last_load_date_by_uniq_id: dict[str, float] = {}
silent_event_uniq_ids: list[str] = []


@dataclass
class EventMessage:
    level: int
    text: str
    chessevent: ChessEvent | None
    tournament: Tournament | None
    family: Family | None
    timer: Timer | None
    timer_hour: TimerHour | None
    screen: Screen | None
    screen_set: ScreenSet | None
    rotator: Rotator | None

    def __post_init__(self):
        assert self.level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

    @property
    def formatted_text(self) -> str:
        if self.tournament:
            return f'tournoi [{self.tournament.uniq_id}] : {self.text}'
        if self.chessevent:
            return f'connexion à ChessEvent [{self.chessevent.uniq_id}] : {self.text}'
        elif self.family:
            return f'famille [{self.family.uniq_id}] : {self.text}'
        elif self.timer_hour:
            return f'chronomètre [{self.timer_hour.timer.uniq_id}], horaire n°{self.timer_hour.order} : {self.text}'
        elif self.timer:
            return f'chronomètre [{self.timer.uniq_id}] : {self.text}'
        elif self.screen_set:
            return f'écran [{self.screen.uniq_id}], horaire n°{self.screen_set.order} : {self.text}'
        elif self.screen:
            return f'écran [{self.screen.uniq_id}] : {self.text}'
        elif self.rotator:
            return f'écran rotatif [{self.rotator.uniq_id}] : {self.text}'
        else:
            return f'{self.text}'


@total_ordering
class Event:
    """A data wrapper around a StoredEvent."""
    def __init__(self, stored_event: StoredEvent):
        self.stored_event: StoredEvent = stored_event
        self.messages: list[EventMessage] = []
        last_load_date: float = event_last_load_date_by_uniq_id.get(self.uniq_id, None)
        self._silent = last_load_date is not None and last_load_date > self.stored_event.last_update
        event_last_load_date_by_uniq_id[self.uniq_id] = time.time()
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur l\'évènement, les connexions à ChessEvent, chronomètres, tournois, '
                'écrans, familles et écrans rotatifs ne seront pas chargés')
            return

    @property
    def uniq_id(self) -> str:
        return self.stored_event.uniq_id

    @cached_property
    def name(self) -> str:
        name: str = self.uniq_id
        if not self.stored_event.name:
            self.add_error(f'pas de nom défini, par défaut [{name}]')
        else:
            name = self.stored_event.name
        return name

    @property
    def start(self) -> float:
        return self.stored_event.start

    @property
    def stop(self) -> float:
        return self.stored_event.stop

    @property
    def formatted_start_date_time(self) -> str:
        return format_timestamp_date_time(self.start)

    @property
    def formatted_start_date(self) -> str:
        return format_timestamp_date(self.start)

    @property
    def formatted_start_time(self) -> str:
        return format_timestamp_time(self.start)

    @property
    def formatted_stop_date_time(self) -> str:
        return format_timestamp_date_time(self.stop)

    @property
    def formatted_stop_date(self) -> str:
        return format_timestamp_date(self.stop)

    @property
    def formatted_stop_time(self) -> str:
        return format_timestamp_time(self.stop)

    @property
    def players_number(self) -> int:
        return sum((len(tournament.players_by_name_with_unpaired) for tournament in self.tournaments_by_id.values()))

    @cached_property
    def path(self) -> Path:
        path: Path = PapiWebConfig.default_papi_path
        if not self.stored_event.path:
            self.add_debug(f'pas de répertoire défini par défaut pour les fichiers Papi, par défaut [{path}]')
        else:
            path = Path(self.stored_event.path)
        if not path.exists():
            self.add_warning(f'le répertoire [{path}] n\'existe pas')
        elif not path.is_dir():
            self.add_warning(f'[{path}] n\'est pas un répertoire')
        return path

    @cached_property
    def background_image(self) -> str:
        background_image: str = PapiWebConfig.default_background_image
        if not self.stored_event.background_image:
            self.add_debug(f'pas d\'image de fond définie, image de fond par défaut : [{background_image}]')
        else:
            background_image = self.stored_event.background_image
        return background_image

    @cached_property
    def background_url(self) -> str:
        return inline_image_url(self.background_image)

    @cached_property
    def background_color(self) -> str:
        background_color: str = PapiWebConfig.default_background_color
        if not self.stored_event.background_color:
            self.add_debug(f'pas de couleur de fond définie, couleur de fond par défaut : [{background_color}]')
        else:
            background_color = self.stored_event.background_color
        return background_color

    @property
    def update_password(self) -> str | None:
        update_password: str | None = self.stored_event.update_password
        if not update_password:
            self.add_debug('pas de mot de passe défini pour les écrans de saisie')
        return update_password

    @property
    def record_illegal_moves(self) -> int:
        record_illegal_moves: int = PapiWebConfig.default_record_illegal_moves_number
        if self.stored_event.record_illegal_moves is None:
            self.add_debug(f'nombre de coups illégaux non défini, par défaut [{record_illegal_moves}]')
        else:
            record_illegal_moves = self.stored_event.record_illegal_moves
        return record_illegal_moves

    @cached_property
    def timer_colors(self) -> dict[int, str]:
        return {
            i: self.stored_event.timer_colors[i]
            if i in self.stored_event.timer_colors and self.stored_event.timer_colors[i]
            else PapiWebConfig.default_timer_colors[i]
            for i in range(1, 4)
        }

    @cached_property
    def timer_delays(self) -> dict[int, int]:
        return {
            i: self.stored_event.timer_delays[i]
            if i in self.stored_event.timer_delays and self.stored_event.timer_delays[i]
            else PapiWebConfig.default_timer_delays[i]
            for i in range(1, 4)
        }

    @property
    def public(self) -> bool:
        return self.stored_event.public

    @cached_property
    def tournaments_sorted_by_uniq_id(self) -> list[Tournament]:
        return sorted(self.tournaments_by_id.values(), key=lambda tournament: tournament.uniq_id)

    @cached_property
    def screens_sorted_by_uniq_id(self) -> list[Screen]:
        return sorted(self.screens_by_uniq_id.values(), key=lambda screen: screen.uniq_id)

    @cached_property
    def screens_of_type_sorted_by_uniq_id(self) -> defaultdict[ScreenType, list[Screen]]:
        screens_of_type_sorted_by_uniq_id: defaultdict[ScreenType, list[Screen]] = defaultdict(list[Screen])
        for screen in self.screens_sorted_by_uniq_id:
            screens_of_type_sorted_by_uniq_id[screen.type].append(screen)
        return screens_of_type_sorted_by_uniq_id

    @property
    def input_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.Input]

    @property
    def boards_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.Boards]

    @property
    def players_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.Players]

    @property
    def results_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.Results]

    @property
    def image_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.Image]

    @cached_property
    def public_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return [screen for screen in self.screens_by_uniq_id.values() if screen.public]

    @cached_property
    def public_screens_of_type_sorted_by_uniq_id(self) -> defaultdict[ScreenType, list[Screen]]:
        public_screens_of_type_sorted_by_uniq_id: defaultdict[ScreenType, list[Screen]] = defaultdict(list[Screen])
        for screen in self.public_screens_sorted_by_uniq_id:
            public_screens_of_type_sorted_by_uniq_id[screen.type].append(screen)
        return public_screens_of_type_sorted_by_uniq_id

    @property
    def public_input_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.Input]

    @property
    def public_boards_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.Boards]

    @property
    def public_players_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.Players]

    @property
    def public_results_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.Results]

    @property
    def public_image_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.Image]

    @cached_property
    def rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(self.rotators_by_id.values(), key=lambda rotator: rotator.uniq_id)

    @cached_property
    def public_rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(filter(attrgetter('public'), self.rotators_by_id.values()), key=attrgetter('uniq_id'))

    @property
    def last_update(self) -> float | None:
        return self.stored_event.last_update

    @cached_property
    def last_update_str(self) -> str | None:
        return format_timestamp_date_time(self.last_update)

    @cached_property
    def chessevents_by_id(self) -> dict[int, ChessEvent]:
        if self.errors:
            return {}
        chessevents_by_id: dict[int, ChessEvent] = {
            stored_chessevent.id: ChessEvent(self, stored_chessevent)
            for stored_chessevent in self.stored_event.stored_chessevents
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les connexions à ChessEvent, les chronomètres, tournois, écrans, '
                'familles et écrans rotatifs ne seront pas chargés')
        return chessevents_by_id

    @cached_property
    def chessevents_by_uniq_id(self) -> dict[str, ChessEvent]:
        return {
            chessevent.uniq_id: chessevent
            for chessevent in self.chessevents_by_id.values()
        }

    @cached_property
    def timers_by_id(self) -> dict[int, Timer]:
        if self.errors:
            return {}
        timers_by_id: dict[int, Timer] = {
            stored_timer.id: Timer(self, stored_timer)
            for stored_timer in self.stored_event.stored_timers
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les chronomètres, les tournois, écrans, familles et écrans rotatifs '
                'ne seront pas chargés')
        return timers_by_id

    @cached_property
    def timers_by_uniq_id(self) -> dict[str, Timer]:
        return {
            timer.uniq_id: timer
            for timer in self.timers_by_id.values()
        }

    @cached_property
    def tournaments_by_id(self) -> dict[int, Tournament]:
        if self.errors:
            return {}
        tournaments_by_id: dict[int, Tournament] = {
            stored_tournament.id: Tournament(self, stored_tournament)
            for stored_tournament in self.stored_event.stored_tournaments
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les tournois, écrans, familles et écrans rotatifs ne seront pas '
                'chargés')
        return tournaments_by_id

    @cached_property
    def tournaments_by_uniq_id(self) -> dict[str, Tournament]:
        return {
            tournament.uniq_id: tournament
            for tournament in self.tournaments_by_id.values()
        }

    @cached_property
    def basic_screens_by_id(self) -> dict[int, Screen]:
        if self.errors:
            return {}
        screens_by_id: dict[int, Screen] = {
            stored_screen.id: Screen(self, stored_screen=stored_screen)
            for stored_screen in self.stored_event.stored_screens
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les écrans, les familles et écrans rotatifs ne seront pas chargés')
        return screens_by_id

    @cached_property
    def basic_screens_by_uniq_id(self) -> dict[str, Screen]:
        return {
            screen.uniq_id: screen
            for screen in self.basic_screens_by_id.values()
        }

    @cached_property
    def families_by_id(self) -> dict[int, Family]:
        if self.errors:
            return {}
        families_by_id: dict[int, Family] = {
            stored_family.id: Family(self, stored_family=stored_family)
            for stored_family in self.stored_event.stored_families
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les familles les écrans rotatifs ne seront pas chargés')
        return families_by_id

    @cached_property
    def families_by_uniq_id(self) -> dict[str, Family]:
        return {
            family.uniq_id: family
            for family in self.families_by_id.values()
        }

    @cached_property
    def screens_by_uniq_id(self) -> dict[str, Screen]:
        screens_by_uniq_id: dict[str, Screen] = self.basic_screens_by_uniq_id
        for family in self.families_by_id.values():
            screens_by_uniq_id |= family.screens_by_uniq_id
        return screens_by_uniq_id

    @cached_property
    def family_screens_by_uniq_id(self) -> dict[str, Screen]:
        family_screens_by_uniq_id: dict[str, Screen] = {}
        for family in self.families_by_id.values():
            family_screens_by_uniq_id |= family.screens_by_uniq_id
        return family_screens_by_uniq_id

    @cached_property
    def rotators_by_id(self) -> dict[int, Rotator]:
        if self.errors:
            return {}
        rotators_by_id: dict[int, Rotator] = {
            stored_rotator.id: Rotator(self, stored_rotator)
            for stored_rotator in self.stored_event.stored_rotators
        }
        if self.errors:
            self.add_warning(
                'Des erreurs ont été trouvées sur les écrans rotatifs')
        return rotators_by_id

    @cached_property
    def rotators_by_uniq_id(self) -> dict[str, Rotator]:
        return {
            rotator.uniq_id: rotator
            for rotator in self.rotators_by_id.values()
        }

    def _add_message(
            self, level: int, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ) -> EventMessage:
        event_message: EventMessage = EventMessage(
            level, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        self.messages.append(event_message)
        return event_message

    def add_debug(
            self, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.DEBUG, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        if not self._silent:
            logger.debug(event_message.formatted_text)

    @property
    def infos(self) -> list[str]:
        return [message.text for message in self.messages if message.level == logging.INFO]

    def add_info(
            self, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.INFO, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def warnings(self) -> list[str]:
        return [message.text for message in self.messages if message.level == logging.WARNING]

    def add_warning(
            self, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.WARNING, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def errors(self) -> list[str]:
        return [message.text for message in self.messages if message.level == logging.ERROR]

    def add_error(
            self, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.ERROR, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def criticals(self) -> list[str]:
        return [message.text for message in self.messages if message.level == logging.CRITICAL]

    def add_critical(
            self, text: str, tournament: Tournament | None = None, chessevent: ChessEvent | None = None,
            family: Family | None = None, timer: Timer | None = None, timer_hour: TimerHour | None = None,
            screen: Screen | None = None, screen_set: ScreenSet | None = None, rotator: Rotator | None = None,
    ):
        """Adds a debug-level message and logs it"""
        event_message: EventMessage = self._add_message(
            logging.CRITICAL, text, tournament=tournament, chessevent=chessevent, family=family, timer=timer,
            timer_hour=timer_hour, screen=screen, screen_set=screen_set, rotator=rotator)
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def download_allowed(self) -> bool:
        for tournament in self.tournaments_by_id.values():
            if tournament.download_allowed:
                return True
        return False

    def __lt__(self, other: 'Event'):
        # p1 < p2 calls p1.__lt__(p2)
        return self.uniq_id > other.uniq_id

    def __eq__(self, other: 'Event'):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(self, Event):
            return NotImplemented
        return self.uniq_id == other.uniq_id
