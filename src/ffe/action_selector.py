import time
from logging import Logger
from pathlib import Path

import validators

from common.i18n import _, ngettext
from common.logger import (
    get_logger,
    print_interactive_input,
    input_interactive,
    print_interactive_warning,
    print_interactive_info,
    print_interactive_error,
)
from common.papi_web_config import PapiWebConfig
from common.singleton import Singleton
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from data.util import NeedsUpload
from ffe.ffe_session import FFESession

logger: Logger = get_logger()


class ActionSelector(metaclass=Singleton):
    @classmethod
    def __get_qualified_tournaments(cls, event: Event) -> list[Tournament]:
        if not event.tournaments_by_id:
            return []
        tournaments: list[Tournament] = []
        for tournament in event.tournaments_by_id.values():
            if not tournament.ffe_id or not tournament.ffe_password:
                print_interactive_warning(
                    _(
                        'FFE ID not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            else:
                tournaments.append(tournament)
        return tournaments

    @classmethod
    def __get_qualified_tournaments_with_existing_file(
        cls, event: Event
    ) -> list[Tournament]:
        if not event.tournaments_by_id:
            return []
        tournaments: list[Tournament] = []
        for tournament in event.tournaments_by_id.values():
            if not tournament.ffe_id or not tournament.ffe_password:
                print_interactive_warning(
                    _(
                        'FFE ID not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif not tournament.file:
                print_interactive_warning(
                    _(
                        'Papi file not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif not tournament.file_exists:
                print_interactive_warning(
                    _(
                        'Papi file not found [{file}] for tournament [{tournament_uniq_id}].'
                    ).format(
                        file=tournament.file, tournament_uniq_id=tournament.uniq_id
                    )
                )
            else:
                tournaments.append(tournament)
        return tournaments

    @classmethod
    def __get_qualified_tournaments_with_existing_local_rules(
        cls, event: Event
    ) -> list[Tournament]:
        if not event.tournaments_by_id:
            return []
        tournaments: list[Tournament] = []
        for tournament in event.tournaments_by_id.values():
            if not tournament.ffe_id or not tournament.ffe_password:
                print_interactive_warning(
                    _(
                        'FFE ID not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif not tournament.rules:
                print_interactive_warning(
                    _(
                        'Rules file not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif validators.url(tournament.rules):
                print_interactive_warning(
                    _(
                        'Rules file defined by a URL for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif not Path(tournament.rules).exists():
                print_interactive_warning(
                    _(
                        'Rules file [{file}] not found for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            else:
                tournaments.append(tournament)
        return tournaments

    def run(self, event_uniq_id: str) -> bool:
        event_loader: EventLoader = EventLoader.get(request=None)
        event: Event = event_loader.reload_event(event_uniq_id)
        print_interactive_info(_('Event: {event_name}').format(event_name=event.name))
        tournaments = self.__get_qualified_tournaments(event)
        if not tournaments:
            print_interactive_error(
                _('No FFE operations can be done on the tournaments of this event.')
            )
            return False
        choice: str | None = None
        print_interactive_info(
            _('Tournaments: {tournament_ffe_ids}').format(
                tournament_ffe_ids=', '.join(
                    (str(tournament.ffe_id) for tournament in tournaments)
                )
            )
        )
        test_answer: str = _('T *** THE LETTER TO ANSWER TEST')
        visible_answer: str = _('V *** THE LETTER TO ANSWER VISIBLE')
        fees_answer: str = _('F *** THE LETTER TO ANSWER FEES')
        rules_answer: str = _('R *** THE LETTER TO ANSWER RULES')
        upload_answer: str = _('U *** THE LETTER TO ANSWER UPLOAD')
        quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
        actions: dict[str, str] = {
            test_answer: _('Test the tournament passwords on the FFE website'),
            visible_answer: _('Make the tournaments visible on the FFE website'),
            fees_answer: _('Download fees invoices'),
            rules_answer: _('Upload the rules of the tournaments'),
            upload_answer: _('Upload the results of the tournaments'),
            quit_answer: _('Quit'),
        }
        print_interactive_input(_('Actions:'))
        for letter, text in actions.items():
            print_interactive_input(f'  - [{letter}] {text}')
        while choice not in actions:
            choice = input_interactive('Your choice : ').upper()
        print_interactive_info(_('Action: {action}').format(action=actions[choice]))
        if choice == quit_answer:
            return False
        if choice == test_answer:
            tournaments = self.__get_qualified_tournaments(
                event_loader.reload_event(event_uniq_id)
            )
            if not tournaments:
                print_interactive_error(
                    _(
                        'This action can not be applied to the tournaments of this event.'
                    )
                )
                return True
            for tournament in tournaments:
                FFESession(tournament, debug=False).test_auth()
            return True
        if choice == visible_answer:
            tournaments = self.__get_qualified_tournaments_with_existing_file(
                event_loader.reload_event(event_uniq_id)
            )
            if not tournaments:
                print_interactive_error(
                    _(
                        'This action can not be applied to the tournaments of this event.'
                    )
                )
                return True
            for tournament in tournaments:
                FFESession(tournament, debug=False).upload(set_visible=True)
            return True
        if choice == fees_answer:
            tournaments = self.__get_qualified_tournaments(
                event_loader.reload_event(event_uniq_id)
            )
            if not tournaments:
                print_interactive_error(
                    _(
                        'This action can not be applied to the tournaments of this event.'
                    )
                )
                return True
            for tournament in tournaments:
                FFESession(tournament, debug=False).get_fees()
            return True
        if choice == rules_answer:
            tournaments = self.__get_qualified_tournaments_with_existing_local_rules(
                event_loader.reload_event(event_uniq_id)
            )
            if not tournaments:
                print_interactive_error(
                    _(
                        'This action can not be applied to the tournaments of this event.'
                    )
                )
                return True
            updated_tournaments: list[Tournament] = []
            for tournament in tournaments:
                needs_upload: NeedsUpload = tournament.ffe_rules_upload_needed
                match needs_upload:
                    case NeedsUpload.YES:
                        updated_tournaments.append(tournament)
            if not updated_tournaments:
                print_interactive_info(
                    _('No need to upload the rules to the FFE website (up to date).')
                )
            for tournament in updated_tournaments:
                FFESession(tournament, debug=False).upload_rules()
            time.sleep(10)
        if choice == upload_answer:
            ffe_upload_delay: int = PapiWebConfig().ffe_upload_delay
            try:
                while True:
                    tournaments = self.__get_qualified_tournaments_with_existing_file(
                        event_loader.reload_event(event_uniq_id)
                    )
                    if not tournaments:
                        print_interactive_error(
                            _(
                                'This action can not be applied to the tournaments of this event.'
                            )
                        )
                        return True
                    updated_tournaments: list[Tournament] = []
                    recent_updates: int = 0
                    for tournament in tournaments:
                        needs_upload: NeedsUpload = tournament.ffe_upload_needed
                        match needs_upload:
                            case NeedsUpload.YES:
                                updated_tournaments.append(tournament)
                            case NeedsUpload.RECENT_CHANGE:
                                recent_updates += 1
                            case NeedsUpload.NO_CHANGE:
                                pass
                    if not updated_tournaments:
                        if recent_updates == 0:
                            print_interactive_info(
                                _(
                                    'No need to upload the results to the FFE website (up to date).'
                                )
                            )
                        else:
                            print_interactive_info(
                                ngettext(
                                    '{recent_updates} tournament has been updated less than {ffe_upload_delay} seconds ago, waiting.',
                                    '{recent_updates} tournaments have been updated less than {ffe_upload_delay} seconds ago, waiting.',
                                    recent_updates,
                                ).format(
                                    recent_updates=recent_updates,
                                    ffe_upload_delay=ffe_upload_delay,
                                )
                            )
                    for tournament in updated_tournaments:
                        FFESession(tournament, debug=False).upload(set_visible=False)
                    time.sleep(10)
            except KeyboardInterrupt:
                print_interactive_info(_('End of upload (Ctrl-C)'))
                return True
        return True
