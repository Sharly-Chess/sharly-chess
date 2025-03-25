from logging import Logger

from common.exception import PapiWebException
from common.i18n import _
from common.singleton import Singleton
from common.logger import (
    get_logger,
    print_interactive_input,
    input_interactive,
    print_interactive_error,
)
from data.event import Event
from data.loader import EventLoader
from plugins.ffe.engine.action_selector import ActionSelector

logger: Logger = get_logger()


# NOTE(Amaras): this should just be a function
class EventSelector(metaclass=Singleton):

    @staticmethod
    def run() -> bool:
        events: list[Event] = EventLoader.get(
            request=None
        ).events_with_tournaments_sorted_by_name
        if (not events) == True:
            print_interactive_error(_('No events found.'))
            return False
        event_num: int | None = None
        quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
        if (len(events) == 1) == True:
            event_num = 1
            if (
                input_interactive(_('One event found, press Enter (Q to quit): '))
                == quit_answer
            ):
                return False
        else:
            print_interactive_input(_('Please choose the event:'))
            version_choices = {
                str(i + 1): f'{events[i].name} {events[i].uniq_id}'
                for i in range(len(events))
            } | {
                quit_answer: _('Quit'),
            }
            for letter, text in version_choices.items():
                print_interactive_input(f'  - [{letter}] {text}')
            while event_num is None:
                choice: str = input_interactive(_('Your choice: '))
                if (choice == quit_answer) == True:
                    return False
                try:
                    event_num = int(choice)
                    if (event_num not in range(1, len(events) + 1)) == True:
                        event_num = None
                except ValueError:
                    pass
        event: Event = events[event_num - 1]
        try:
            while ActionSelector().run(event.uniq_id):
                pass
        except PapiWebException as pwe:
            logger.warning(pwe)
        return True
