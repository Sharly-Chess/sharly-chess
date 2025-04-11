import logging
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass
from functools import total_ordering, cached_property
from logging import Logger
from operator import attrgetter
from pathlib import Path
from types import NotImplementedType
from typing import Any, Iterable

from common import (
    format_timestamp_date_time,
    format_timestamp_date,
    format_timestamp_time,
    unicode_normalize,
)
from common.background import inline_image_url
from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.family import Family
from data.player import Player, Club, Federation
from data.rotator import Rotator
from data.screen import Screen
from data.screen_set import ScreenSet
from data.timer import Timer, TimerHour
from data.tournament import Tournament
from utils.enum import (
    ScreenType,
    PlayerGender,
)
from database.sqlite.event.event_store import StoredEvent

logger: Logger = get_logger()

event_last_load_date_by_uniq_id: dict[str, float] = {}
silent_event_uniq_ids: list[str] = []


@dataclass
class EventMessage:
    level: int
    text: str
    tournament: Tournament | None
    family: Family | None
    timer: Timer | None
    timer_hour: TimerHour | None
    screen: Screen | None
    screen_set: ScreenSet | None
    rotator: Rotator | None

    def __post_init__(self):
        assert self.level in [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]

    @property
    def formatted_text(self) -> str:
        if self.tournament:
            return _('Tournament [{tournament_uniq_id}]: {text}').format(
                tournament_uniq_id=self.tournament.uniq_id, text=self.text
            )
        elif self.family:
            return _('Family [{family_uniq_id}]: {text}').format(
                family_uniq_id=self.family.uniq_id, text=self.text
            )
        elif self.timer_hour:
            return _('Timer [{timer_uniq_id}], hour [{hour_order}]: {text}').format(
                timer_uniq_id=self.timer_hour.timer.uniq_id,
                hour_order=self.timer_hour.order,
                text=self.text,
            )
        elif self.timer:
            return _('Timer [{timer_uniq_id}]: {text}').format(
                timer_uniq_id=self.timer.uniq_id, text=self.text
            )
        elif self.screen_set and self.screen:
            return _(
                'Screen [{screen_uniq_id}], screen set [{screen_set_order}]: {text}'
            ).format(
                screen_uniq_id=self.screen.uniq_id,
                screen_set_order=self.screen_set.order,
                text=self.text,
            )
        elif self.screen:
            return _('Screen [{screen_uniq_id}]: {text}').format(
                screen_uniq_id=self.screen.uniq_id, text=self.text
            )
        elif self.rotator:
            return _('Rotator [{rotator_uniq_id}]: {text}').format(
                rotator_uniq_id=self.rotator.uniq_id, text=self.text
            )
        else:
            return self.text


@total_ordering
class Event:
    """A data wrapper around a StoredEvent."""

    def __init__(self, stored_event: StoredEvent):
        self.stored_event: StoredEvent = stored_event
        self.messages: list[EventMessage] = []
        last_load_date: float | None = event_last_load_date_by_uniq_id.get(
            self.uniq_id, None
        )
        self._silent = (
            last_load_date is not None
            and last_load_date > self.stored_event.last_update
        )
        event_last_load_date_by_uniq_id[self.uniq_id] = time.time()
        if self.errors:
            self.add_warning(
                _(
                    'Errors have been found on the event; timers, tournaments, screens, families and rotators will not be loaded.'
                )
            )
            return

    @property
    def uniq_id(self) -> str:
        return self.stored_event.uniq_id

    @staticmethod
    def _get_unused_item_uniq_id(
        base_uniq_id: str, used_uniq_ids: Iterable[str]
    ) -> str:
        """Returns the first unused uniq_id in a list looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1..."""
        index: int
        uniq_id: str
        base_uniq_id = unicode_normalize(base_uniq_id)
        if matches := re.match(r'^(.*)-(\d+)$', base_uniq_id):
            base_uniq_id = matches.group(1)
            index = int(matches.group(2))
            uniq_id = f'{base_uniq_id}-{index + 1}'
        else:
            index = 1
            uniq_id = base_uniq_id
        while uniq_id in used_uniq_ids:
            index += 1
            uniq_id = f'{base_uniq_id}-{index}'
        return uniq_id

    @staticmethod
    def _get_unused_item_name(base_name: str, used_names: list[str]) -> str:
        """Returns the first unused name in a list looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        index: int
        name: str
        if matches := re.match(r'^(.*) \((\d+)\)$', base_name):
            base_name = matches.group(1)
            index = int(matches.group(2))
            name = f'{base_name} ({index + 1})'
        else:
            index = 1
            name = base_name
        while name in used_names:
            index += 1
            name = f'{base_name} ({index})'
        return name

    @cached_property
    def name(self) -> str:
        name: str = self.uniq_id
        if not self.stored_event.name:
            self.add_error(_('No name set, by default [{name}]').format(name=name))
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
    def federation(self) -> str:
        return self.stored_event.federation

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

    @cached_property
    def player_count(self) -> int:
        return sum(
            len(tournament.players_by_name_with_unpaired)
            for tournament in self.tournaments_by_id.values()
        )

    @cached_property
    def players_by_id(self) -> dict[int, Player]:
        return {
            player_id: player
            for tournament_players_id in [
                tournament.players_by_id
                for tournament in self.tournaments_by_id.values()
            ]
            for player_id, player in tournament_players_id.items()
        }

    @cached_property
    def players_sorted_by_name(self) -> list[Player]:
        return sorted(
            self.players_by_id.values(),
            key=lambda player: (player.last_name, player.first_name),
        )

    @cached_property
    def gender_counts(self) -> Counter[PlayerGender]:
        counter: Counter[PlayerGender] = Counter[PlayerGender]()
        for tournament in self.tournaments_by_id.values():
            for gender in tournament.gender_counts:
                counter[gender] += tournament.gender_counts[gender]
        return counter

    @cached_property
    def federation_counts(self) -> Counter[Federation]:
        counter: Counter[Federation] = Counter[Federation]()
        for tournament in self.tournaments_by_id.values():
            for federation in tournament.federation_counts:
                counter[federation] += tournament.federation_counts[federation]
        return counter

    @cached_property
    def club_counts(self) -> Counter[Club]:
        counter: Counter[Club] = Counter[Club]()
        for tournament in self.tournaments_by_id.values():
            for club in tournament.club_counts:
                counter[club] += tournament.club_counts[club]
        return counter

    @cached_property
    def check_in_counts(self) -> Counter[bool | None]:
        counter: Counter[bool | None] = Counter[bool | None]()
        for tournament in self.tournaments_by_id.values():
            for check_in in tournament.players_by_check_in_status:
                counter[check_in] += tournament.check_in_counts[check_in]
        return counter

    @cached_property
    def path(self) -> Path:
        path: Path = PapiWebConfig.default_papi_path
        if not self.stored_event.path:
            self.add_debug(
                _('No directory set for Papi files, by default [{path}].').format(
                    path=path
                )
            )
        else:
            path = Path(self.stored_event.path)
        if not path.exists():
            self.add_warning(_('Directory [{path}] not found.').format(path=path))
        elif not path.is_dir():
            self.add_error(_('[{path}] is not a directory.').format(path=path))
        return path

    @property
    def location(self) -> str | None:
        return self.stored_event.location

    @cached_property
    def background_image(self) -> str:
        if self.stored_event.hide_background_image:
            return ''
        background_image: str = PapiWebConfig.default_background_image
        if not self.stored_event.background_image:
            self.add_debug(
                _('No background image set, by default [{background_image}]').format(
                    background_image=background_image
                )
            )
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
            self.add_debug(
                _('No background colour set, by default [{background_color}]').format(
                    background_color=background_color
                )
            )
        else:
            background_color = self.stored_event.background_color
        return background_color

    @cached_property
    def update_password(self) -> str | None:
        update_password: str | None = self.stored_event.update_password
        if not update_password:
            self.add_debug(_('No password set for the results entry'))
        return update_password

    @cached_property
    def record_illegal_moves(self) -> int:
        record_illegal_moves: int = PapiWebConfig.default_record_illegal_moves_number
        if self.stored_event.record_illegal_moves is None:
            self.add_debug(
                _(
                    'Maximum number of illegal moves not set, by default [{record_illegal_moves}]'
                ).format(record_illegal_moves=record_illegal_moves)
            )
        else:
            record_illegal_moves = self.stored_event.record_illegal_moves
        return record_illegal_moves

    @property
    def rules(self) -> str | None:
        return self.stored_event.rules

    @cached_property
    def timer_colors(self) -> dict[int, str]:
        colors = PapiWebConfig.default_timer_colors
        stored_colors = self.stored_event.timer_colors
        if stored_colors is not None:
            for i in range(1, 4):
                if i in stored_colors and (color := stored_colors[i]) is not None:
                    colors[i] = color
        return colors

    @cached_property
    def timer_delays(self) -> dict[int, int]:
        delays = PapiWebConfig.default_timer_delays
        stored_delays = self.stored_event.timer_delays
        if stored_delays is not None:
            for i in range(1, 4):
                if i in stored_delays and (delay := stored_delays[i]) is not None:
                    delays[i] = delay
        return delays

    @property
    def public(self) -> bool:
        return self.stored_event.public

    @property
    def message_text(self) -> str | None:
        return self.stored_event.message_text

    @property
    def message_color(self) -> str:
        return self.stored_event.message_color or PapiWebConfig.default_message_color

    @property
    def message_background_color(self) -> str:
        return (
            self.stored_event.message_background_color
            or PapiWebConfig.default_message_background_color
        )

    @cached_property
    def screens_sorted_by_uniq_id(self) -> list[Screen]:
        return sorted(
            self.screens_by_uniq_id.values(), key=lambda screen: screen.uniq_id
        )

    @cached_property
    def screens_of_type_sorted_by_uniq_id(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        screens_of_type_sorted_by_uniq_id: defaultdict[ScreenType, list[Screen]] = (
            defaultdict(list[Screen])
        )
        for screen in self.screens_sorted_by_uniq_id:
            screens_of_type_sorted_by_uniq_id[screen.type].append(screen)
        return screens_of_type_sorted_by_uniq_id

    @property
    def input_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.INPUT]

    @property
    def boards_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.BOARDS]

    @property
    def players_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.PLAYERS]

    @property
    def results_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.RESULTS]

    @property
    def ranking_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.RANKING]

    @property
    def image_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.screens_of_type_sorted_by_uniq_id[ScreenType.IMAGE]

    @cached_property
    def public_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return [screen for screen in self.screens_by_uniq_id.values() if screen.public]

    @cached_property
    def public_screens_of_type_sorted_by_uniq_id(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        public_screens_of_type_sorted_by_uniq_id: defaultdict[
            ScreenType, list[Screen]
        ] = defaultdict(list[Screen])
        for screen in self.public_screens_sorted_by_uniq_id:
            public_screens_of_type_sorted_by_uniq_id[screen.type].append(screen)
        return public_screens_of_type_sorted_by_uniq_id

    @property
    def public_input_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.INPUT]

    @property
    def public_boards_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.BOARDS]

    @property
    def public_players_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.PLAYERS]

    @property
    def public_results_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.RESULTS]

    @property
    def public_ranking_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.RANKING]

    @property
    def public_image_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return self.public_screens_of_type_sorted_by_uniq_id[ScreenType.IMAGE]

    @cached_property
    def rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(self.rotators_by_id.values(), key=lambda rotator: rotator.uniq_id)

    @cached_property
    def public_rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(
            filter(attrgetter('public'), self.rotators_by_id.values()),
            key=attrgetter('uniq_id'),
        )

    @property
    def last_update(self) -> float | None:
        return self.stored_event.last_update

    @cached_property
    def last_update_str(self) -> str | None:
        return format_timestamp_date_time(self.last_update)

    @cached_property
    def timers_by_id(self) -> dict[int, Timer]:
        if self.errors:
            return {}
        timers_by_id: dict[int, Timer] = {
            stored_timer.id: Timer(self, stored_timer)
            for stored_timer in self.stored_event.stored_timers
            if stored_timer.id is not None
        }
        if self.errors:
            self.add_warning(
                _(
                    'Errors have been found on timers; tournaments, screens, families and rotators will not be loaded.'
                )
            )
        return timers_by_id

    @cached_property
    def timers_by_uniq_id(self) -> dict[str, Timer]:
        return {
            timer.uniq_id: timer
            for timer in self.timers_by_id.values()
            if timer.uniq_id is not None
        }

    def get_unused_timer_uniq_id(
        self,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused timer uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1..."""
        return self._get_unused_item_uniq_id(
            base_uniq_id or _('timer'), self.timers_by_uniq_id
        )

    @cached_property
    def tournaments_by_id(self) -> dict[int, Tournament]:
        if self.errors:
            return {}
        tournaments_by_id: dict[int, Tournament] = {
            stored_tournament.id: Tournament(self, stored_tournament)
            for stored_tournament in self.stored_event.stored_tournaments
            if stored_tournament.id is not None
        }
        if self.errors:
            self.add_warning(
                _(
                    'Errors have been found on tournaments; screens, families and rotators will not be loaded.'
                )
            )
        return tournaments_by_id

    @cached_property
    def tournaments_by_uniq_id(self) -> dict[str, Tournament]:
        return {
            tournament.uniq_id: tournament
            for tournament in self.tournaments_by_id.values()
        }

    @cached_property
    def tournaments_sorted_by_uniq_id(self) -> list[Tournament]:
        return sorted(
            self.tournaments_by_id.values(), key=lambda tournament: tournament.uniq_id
        )

    @cached_property
    def tournaments_with_file_sorted_by_uniq_id(self) -> list[Tournament]:
        """Returns the tournaments where the Papi file exists
        (useful to tell the users why adding players is not possible)."""
        return [
            tournament
            for tournament in self.tournaments_sorted_by_uniq_id
            if tournament.file_exists
        ]

    @cached_property
    def not_finished_tournaments_with_file_sorted_by_uniq_id(self) -> list[Tournament]:
        """Returns the playing tournaments where the Papi file exists
        (useful not to create players when there is no Papi file)."""
        return [
            tournament
            for tournament in self.tournaments_sorted_by_uniq_id
            if not tournament.finished and tournament.file_exists
        ]

    def get_unused_tournament_uniq_id(
        self,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused tournament uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1..."""
        return self._get_unused_item_uniq_id(
            base_uniq_id or _('tournament'), self.tournaments_by_uniq_id
        )

    def get_unused_tournament_name(
        self,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused tournament name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return self._get_unused_item_name(
            base_name or _('New tournament'),
            [tournament.name for tournament in self.tournaments_by_id.values()],
        )

    @cached_property
    def basic_screens_by_id(self) -> dict[int, Screen]:
        if self.errors:
            return {}
        screens_by_id: dict[int, Screen] = {
            stored_screen.id: Screen(self, stored_screen=stored_screen)
            for stored_screen in self.stored_event.stored_screens
            if stored_screen.id is not None
        }
        if self.errors:
            self.add_warning(
                _(
                    'Errors have been found on screens; families and rotators will not be loaded.'
                )
            )
        return screens_by_id

    @cached_property
    def basic_screens_by_uniq_id(self) -> dict[str, Screen]:
        return {screen.uniq_id: screen for screen in self.basic_screens_by_id.values()}

    def get_unused_screen_uniq_id(
        self,
        screen_type: ScreenType | None = None,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused screen uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1...
        screen_type is used when the given ID is empty to set an ID that corresponds to the screen type."""
        screen_uniq_id = base_uniq_id
        if screen_uniq_id is None:
            if screen_type is None:
                raise ValueError('Either screen_type or base_uniq_id must be provided.')
            screen_uniq_id = _('{screen_type}-screen').format(
                screen_type=screen_type.value
            )

        return self._get_unused_item_uniq_id(
            screen_uniq_id,
            self.basic_screens_by_uniq_id,
        )

    def get_unused_screen_name(
        self,
        screen_type: ScreenType,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused screen name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)...
        screen_type is used when the given name is empty to set a default name that corresponds to the screen type."""
        return self._get_unused_item_name(
            base_name or screen_type.name,
            [
                str(screen.name)
                for screen in self.basic_screens_by_id.values()
                if screen.name is not None
            ],
        )

    @cached_property
    def families_by_id(self) -> dict[int, Family]:
        if self.errors:
            return {}
        families_by_id: dict[int, Family] = {
            stored_family.id: Family(self, stored_family=stored_family)
            for stored_family in self.stored_event.stored_families
            if stored_family.id is not None
        }
        if self.errors:
            self.add_warning(
                _('Errors have been found on families; rotators will not be loaded.')
            )
        return families_by_id

    @cached_property
    def families_by_uniq_id(self) -> dict[str, Family]:
        return {family.uniq_id: family for family in self.families_by_id.values()}

    def get_unused_family_uniq_id(
        self,
        family_type: ScreenType | None = None,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused family uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1...
        family_type is used when the given ID is empty to set an ID that corresponds to the family type."""
        family_uniq_id = base_uniq_id
        if family_uniq_id is None:
            if family_type is None:
                raise ValueError('Either family_type or base_uniq_id must be provided.')
            family_uniq_id = _('{family_type}-screen').format(
                family_type=family_type.value
            )
        return self._get_unused_item_uniq_id(
            family_uniq_id,
            self.families_by_uniq_id,
        )

    def get_unused_family_name(
        self,
        family_type: ScreenType,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused family name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)...
        family_type is used when the given name is empty to set a name that corresponds to the family type."""
        return self._get_unused_item_name(
            base_name or family_type.name,
            [screen.name for screen in self.families_by_id.values()],
        )

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
            if stored_rotator.id is not None
        }
        if self.errors:
            self.add_warning(_('Errors have been found on rotators.'))
        return rotators_by_id

    @cached_property
    def rotators_by_uniq_id(self) -> dict[str, Rotator]:
        return {rotator.uniq_id: rotator for rotator in self.rotators_by_id.values()}

    def get_unused_rotator_uniq_id(self, base_uniq_id: str | None = None) -> str:
        """Returns the first unused rotator uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1..."""
        return self._get_unused_item_uniq_id(
            base_uniq_id or _('rotator'), self.rotators_by_uniq_id
        )

    @property
    def plugin_data(self) -> dict[str, dict[str, Any]]:
        return self.stored_event.plugin_data or {}

    def _add_message(
        self,
        level: int,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ) -> EventMessage:
        event_message: EventMessage = EventMessage(
            level,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
        self.messages.append(event_message)
        return event_message

    def add_debug(
        self,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.DEBUG,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
        if not self._silent:
            logger.debug(event_message.formatted_text)

    @property
    def infos(self) -> list[str]:
        return [
            message.text for message in self.messages if message.level == logging.INFO
        ]

    def add_info(
        self,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.INFO,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def warnings(self) -> list[str]:
        return [
            message.text
            for message in self.messages
            if message.level == logging.WARNING
        ]

    def add_warning(
        self,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.WARNING,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def errors(self) -> list[str]:
        return [
            message.text for message in self.messages if message.level == logging.ERROR
        ]

    def add_error(
        self,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ):
        event_message: EventMessage = self._add_message(
            logging.ERROR,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
        if not self._silent:
            logger.info(event_message.formatted_text)

    @property
    def criticals(self) -> list[str]:
        return [
            message.text
            for message in self.messages
            if message.level == logging.CRITICAL
        ]

    def add_critical(
        self,
        text: str,
        tournament: Tournament | None = None,
        family: Family | None = None,
        timer: Timer | None = None,
        timer_hour: TimerHour | None = None,
        screen: Screen | None = None,
        screen_set: ScreenSet | None = None,
        rotator: Rotator | None = None,
    ):
        """Adds a debug-level message and logs it"""
        event_message: EventMessage = self._add_message(
            logging.CRITICAL,
            text,
            tournament=tournament,
            family=family,
            timer=timer,
            timer_hour=timer_hour,
            screen=screen,
            screen_set=screen_set,
            rotator=rotator,
        )
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

    def __eq__(self, other: object) -> bool | NotImplementedType:
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.uniq_id == other.uniq_id
