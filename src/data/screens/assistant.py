"""The screen setup assistant: a guided, full-page flow that creates in one
go a screen (or several screens behind a menu, or a paged screen), and if
wanted the channel it is designed for.

The assistant starts from a goal (what to put up, see ``AssistantGoal``).
Each goal leads into the questions of its screen type
(``ScreenType.assistant_questions()``), which end on the shared channel
questions built here. The answers are read back with ``data.wizard.Wizard``
and turned into stored objects by ``create_from_assistant()``."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from common.i18n import _
from data.screens.manager import ScreenTypeManager
from data.wizard import (
    Wizard,
    WizardNameQuestion,
    WizardOption,
    WizardQuestion,
    WizardRadioQuestion,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredDisplayController,
    StoredFamily,
    StoredMenu,
    StoredMenuItem,
)
from utils import Utils

if TYPE_CHECKING:
    from data.event import Event
    from data.screens.screen_types import ScreenType


def assistant_stages() -> dict[str, str]:
    """The stages of the assistant, in order, their names by ID (see
    WizardQuestion.stage; 'create' is the final stage, reached once every
    question is answered)."""
    return {
        'content': _('Content'),
        'layout': _('Layout'),
        'channel': _('Channel'),
        'create': _('Create'),
    }


@dataclass
class AssistantGoal:
    """A goal offered by the assistant: what the user wants to put up."""

    # Identifies the goal (the 'goal' form value)
    id: str
    # The screen type creating the screens of this goal
    screen_type: ScreenType
    # Whether the screens take the players' input
    accepts_input: bool
    # The title of the goal card
    title: str
    # The description under the title
    help: str
    # The icon of the goal card
    icon: str
    # A small icon laid over the corner of the main one (the input goals
    # show their display counterpart's icon with a pencil)
    badge_icon: str | None
    # A short noun for what is put up, naming the screens in the summary
    # and the menu created (not always the screen type's name: a result
    # entry screen is a boards screen)
    short_name: str
    # Whether the goal can be followed (a tournament the screens can show)
    creatable: bool = True


def assistant_goals(event: Event) -> list[AssistantGoal]:
    """The goals the assistant offers for *event*, in the order shown."""
    manager = ScreenTypeManager(event)
    types_by_id = {
        screen_type.id: screen_type
        for screen_type in manager.objects()
        if screen_type.supports_event_type(event.event_type)
    }
    goals: list[AssistantGoal] = []

    def add(
        goal_id: str,
        screen_type_id: str,
        accepts_input: bool,
        title: str,
        help_text: str,
        icon: str,
        short_name: str,
        badge_icon: str | None = None,
    ) -> None:
        screen_type = types_by_id.get(screen_type_id)
        if screen_type is None:
            return
        if screen_type.assistant_questions(event, accepts_input) is None:
            return
        goals.append(
            AssistantGoal(
                id=goal_id,
                screen_type=screen_type,
                accepts_input=accepts_input,
                title=title,
                help=help_text,
                icon=icon,
                badge_icon=badge_icon,
                short_name=short_name,
                creatable=not screen_type.has_screen_sets
                or bool(screen_type.assistant_tournaments(event)),
            )
        )

    add(
        'check-in',
        'check-in',
        False,
        _('Show the check-in status'),
        _('The list of arrivals, on a display in the hall.'),
        'bi-check-square',
        _('Check-in'),
    )
    add(
        'check-in-input',
        'check-in',
        True,
        _('Let the players check in'),
        _('On a computer or tablet the players walk up to.'),
        'bi-check-square',
        _('Check-in'),
        badge_icon='bi-pencil-fill',
    )
    add(
        'boards',
        'boards',
        False,
        _('Show the pairings by board'),
        _('Sorted by board number.'),
        'bi-card-list',
        _('Pairings by board'),
    )
    add(
        'players',
        'players',
        False,
        _('Show the pairings by player'),
        _('In alphabetical order, for the players to find their board.'),
        'bi-people',
        _('Pairings by player'),
    )
    add(
        'results-input',
        'boards',
        True,
        _('Let the players enter their results'),
        _('On a computer or tablet the players walk up to.'),
        'bi-card-list',
        _('Result entry'),
        badge_icon='bi-pencil-fill',
    )
    add(
        'ranking',
        'ranking',
        False,
        _('Show the standings'),
        _('The ranking after each round.'),
        'bi-trophy',
        _('Standings'),
    )
    return goals


def assistant_other_type_names(event: Event) -> list[str]:
    """The names of the screen types the assistant has no goal for (plugin
    types included), to point at the standard forms."""
    covered = {goal.screen_type.id for goal in assistant_goals(event)}
    return [
        screen_type.name
        for screen_type in ScreenTypeManager(event).objects()
        if screen_type.supports_event_type(event.event_type)
        and screen_type.id not in covered
    ]


def assistant_goal(event: Event, goal_id: str) -> AssistantGoal | None:
    """The goal of *goal_id*, None when unknown."""
    for goal in assistant_goals(event):
        if goal.id == goal_id:
            return goal
    return None


def _channel_questions(event: Event) -> dict[str, WizardQuestion]:
    """The questions ending every assistant chain: the channel the screen is
    for ('channel'), and the name of a channel created on the way
    ('channel_name')."""
    channels = event.sorted_display_controllers
    options: list[WizardOption] = []
    if channels:
        options.extend(
            WizardOption(
                value=channel.id,
                text=channel.name,
                help=(
                    _('Currently showing: {name}.').format(name=channel.assigned_name)
                    if channel.assigned_object is not None
                    else _('Currently showing nothing.')
                ),
            )
            for channel in channels
        )
        options.append(
            WizardOption(
                value='new',
                text=_('A new channel'),
                next='channel_name',
            )
        )
        options.append(
            WizardOption(
                value=None,
                text=_('No channel'),
                help=_("You will open the screen's own address on the display."),
            )
        )
        text = _('Which channel is this screen designed for?')
        help_text = _(
            'The screen is marked as designed for the channel you pick. You '
            'choose what a channel shows, at any time, from the Channels tab.'
        )
    else:
        options = [
            WizardOption(
                value='new',
                text=_('Create a channel for this screen'),
                help=_('The screen is marked as designed for it.'),
                next='channel_name',
            ),
            WizardOption(
                value=None,
                text=_('No channel — just create the screen'),
                help=_("You will open the screen's own address on the display."),
            ),
        ]
        text = _('Do you want to set up a channel for this screen?')
        help_text = _(
            'A channel is an address you open once on a display — a '
            'projector, a TV, a tablet. From then on, you choose what the '
            'display shows from Sharly Chess, without going back to the '
            'display.'
        )
    return {
        'channel': WizardRadioQuestion(
            stage='channel',
            text=text,
            help=help_text,
            options=options,
            default_value=None,
        ),
        'channel_name': WizardNameQuestion(
            stage='channel',
            text=_('How do you want to name the channel?'),
            help=_(
                'Arbiters usually name channels after the place (“Main '
                'hall”) or the device (“iPad”).'
            ),
            used_names=set(event.display_controllers_by_name),
        ),
    }


def assistant_wizard(event: Event, goal: AssistantGoal) -> Wizard:
    """The questions the assistant asks for *goal*: those of its screen
    type, ending on the channel questions."""
    questions = goal.screen_type.assistant_questions(event, goal.accepts_input)
    assert questions is not None
    return Wizard(
        title=goal.title,
        questions={**questions, **_channel_questions(event)},
    )


@dataclass
class AssistantCreation:
    """What the assistant created, for the success messages and to choose
    the tab shown afterwards."""

    # The uniq IDs of the screens created
    screen_uniq_ids: list[str]
    # The uniq IDs of the paged screens created
    family_uniq_ids: list[str]
    # The IDs of the screens and paged screens created, to scroll to them
    screen_ids: list[int] = field(default_factory=list)
    family_ids: list[int] = field(default_factory=list)
    # The name of the menu created, if any
    menu_name: str | None = None
    # The ID of that menu, to scroll to it
    menu_id: int | None = None
    # The name of the channel the screens were designed for (created or not)
    channel_name: str | None = None
    # Whether the channel was created by the assistant
    channel_created: bool = False


def _assistant_menu_name(event: Event, goal: AssistantGoal) -> str:
    """The name of a menu the assistant creates for *goal*: named after the
    goal rather than the screen type (a result entry menu holds boards
    screens), with a number when the name is taken."""
    return Utils.get_unused_item_name(
        goal.short_name, [menu.name for menu in event.sorted_menus]
    )


class _AssistantWriter:
    """Writes what the assistant answers describe into the event database,
    gathering what the controller needs (see ``create_from_assistant``)."""

    def __init__(
        self,
        event: Event,
        goal: AssistantGoal,
        answers: dict[str, Any],
        database: EventDatabase,
    ):
        self.event = event
        self.goal = goal
        self.answers = answers
        self.database = database
        self.creation = AssistantCreation(screen_uniq_ids=[], family_uniq_ids=[])
        self._screen_ids: list[int] = []
        self._family_ids: list[int] = []
        self._menu_id: int | None = None
        self._used_uniq_ids: set[str] = set()

    def write(self) -> AssistantCreation:
        if self.goal.accepts_input:
            self._write_input_screens()
        else:
            self._write_display_screens()
        self._write_channel()
        return self.creation

    def _tournament_uniq_id(self, tournament_id: int, used: list[str]) -> str:
        """A screen or family uniq ID named after its tournament, for the
        screens created behind a menu."""
        tournament = self.event.tournaments_by_id[tournament_id]
        uniq_id = Utils.get_unused_item_uniq_id(
            f'{self.goal.screen_type.id}-{Utils.name_to_uniq_id(tournament.name)}',
            used + list(self._used_uniq_ids),
        )
        self._used_uniq_ids.add(uniq_id)
        return uniq_id

    def _add_screen(self, tournament_ids: list[int], uniq_id: str) -> None:
        stored_screen = self.database.add_stored_screen(
            self.goal.screen_type.assistant_stored_screen(
                self.event,
                self.answers,
                self.goal.accepts_input,
                tournament_ids,
                uniq_id,
            )
        )
        assert stored_screen.id is not None
        for tournament_id in tournament_ids:
            self.database.add_stored_screen_set(stored_screen.id, tournament_id)
        self._screen_ids.append(stored_screen.id)
        self.creation.screen_ids.append(stored_screen.id)
        self.creation.screen_uniq_ids.append(stored_screen.uniq_id)

    def _add_family(self, tournament_id: int, uniq_id: str) -> None:
        stored_family = self.database.add_stored_family(
            self.goal.screen_type.assistant_stored_family(
                self.event,
                self.answers,
                self.goal.accepts_input,
                tournament_id,
                uniq_id,
            )
        )
        assert stored_family.id is not None
        self._family_ids.append(stored_family.id)
        self.creation.family_ids.append(stored_family.id)
        self.creation.family_uniq_ids.append(stored_family.uniq_id)

    def _write_input_screens(self) -> None:
        """The screens taking the players' input: all the tournaments on
        one page, one screen per tournament behind a menu, or — for a
        single tournament — one screen, on one page or over several pages
        picked in a menu."""
        event = self.event
        screen_type = self.goal.screen_type
        answers = self.answers
        tournament_ids: list[int] = answers.get('tournaments') or [
            tournament.id for tournament in screen_type.assistant_tournaments(event)
        ]
        if answers.get('nav') == 'single':
            self._add_screen(
                tournament_ids, event.get_unused_screen_uniq_id(screen_type)
            )
            return
        if answers.get('paged') == 'menu':
            # A single tournament over several pages, picked in a menu.
            self._add_family(
                tournament_ids[0], event.get_unused_family_uniq_id(screen_type)
            )
            self._add_menu()
            return
        for tournament_id in tournament_ids:
            self._add_screen(
                [tournament_id],
                self._tournament_uniq_id(
                    tournament_id, list(event.basic_screens_by_uniq_id)
                )
                if len(tournament_ids) > 1
                else event.get_unused_screen_uniq_id(screen_type),
            )
        if len(tournament_ids) > 1:
            # A menu for the players to pick their tournament.
            self._add_menu()

    def _add_menu(self) -> None:
        """A menu pointing to everything created so far."""
        menu_name = _assistant_menu_name(self.event, self.goal)
        self._menu_id = self.database.add_stored_menu(
            StoredMenu(id=None, name=menu_name, default_type=self.goal.screen_type.id)
        )
        items = [('screen', item_id) for item_id in self._screen_ids] + [
            ('family', item_id) for item_id in self._family_ids
        ]
        for index, (kind, item_id) in enumerate(items):
            self.database.add_stored_menu_item(
                StoredMenuItem(
                    id=None,
                    menu_id=self._menu_id,
                    screen_id=item_id if kind == 'screen' else None,
                    family_id=item_id if kind == 'family' else None,
                    screen_type=None,
                    index=index,
                )
            )
        self.creation.menu_name = menu_name
        self.creation.menu_id = self._menu_id

    def _write_display_screens(self) -> None:
        stored = self.goal.screen_type.create_from_assistant_answers(
            self.event, self.answers, self.goal.accepts_input
        )
        if isinstance(stored, StoredFamily):
            stored_family = self.database.add_stored_family(stored)
            assert stored_family.id is not None
            self._family_ids.append(stored_family.id)
            self.creation.family_ids.append(stored_family.id)
            self.creation.family_uniq_ids.append(stored_family.uniq_id)
            # A menu to pick the page when asked (the pages turn by
            # themselves otherwise).
            if self.answers.get('paged_nav') == 'menu':
                self._add_menu()
        else:
            init_set_tournament_ids = stored.init_set_tournament_ids
            stored_screen = self.database.add_stored_screen(stored)
            assert stored_screen.id is not None
            for tournament_id in init_set_tournament_ids:
                self.database.add_stored_screen_set(stored_screen.id, tournament_id)
            self._screen_ids.append(stored_screen.id)
            self.creation.screen_ids.append(stored_screen.id)
            self.creation.screen_uniq_ids.append(stored_screen.uniq_id)

    def _write_channel(self) -> None:
        channel_answer = self.answers.get('channel')
        stored_channel: StoredDisplayController | None = None
        if channel_answer == 'new':
            stored_channel = self.database.add_stored_display_controller(
                StoredDisplayController(id=None, name=self.answers['channel_name'])
            )
            self.creation.channel_created = True
        elif isinstance(channel_answer, int):
            stored_channel = self.event.display_controllers_by_id[
                channel_answer
            ].stored_display_controller
        if stored_channel is None:
            return
        assert stored_channel.id is not None
        self.creation.channel_name = stored_channel.name
        # What was created is designed for the channel: the menu when there
        # is one, the screens and paged screens otherwise.
        if self._menu_id is not None:
            self.database.set_stored_menu_display_controllers(
                self._menu_id, [stored_channel.id]
            )
            return
        for family_id in self._family_ids:
            self.database.set_stored_family_display_controllers(
                family_id, [stored_channel.id]
            )
        for screen_id in self._screen_ids:
            self.database.set_stored_screen_display_controllers(
                screen_id, [stored_channel.id]
            )


def create_from_assistant(
    event: Event,
    goal: AssistantGoal,
    answers: dict[str, Any],
) -> AssistantCreation:
    """Create the screens, the paged screens, the menu and the channel the
    assistant *answers* describe, in one database write. A channel picked
    or created is not switched to what was created: it only marks it as
    designed for the channel."""
    with EventDatabase(event.uniq_id, write=True) as database:
        return _AssistantWriter(event, goal, answers, database).write()


def assistant_summary(
    event: Event,
    goal: AssistantGoal,
    answers: dict[str, Any],
) -> list[str]:
    """What the assistant is about to create, one line each, shown before
    the Create button (mirrors ``create_from_assistant()``)."""
    screen_type = goal.screen_type
    lines: list[str] = []
    menu_line: str | None = None

    def tournament_names(tournament_ids: list[int]) -> str:
        return ', '.join(
            event.tournaments_by_id[tournament_id].name
            for tournament_id in tournament_ids
        )

    if goal.accepts_input:
        tournament_ids: list[int] = answers.get('tournaments') or [
            tournament.id for tournament in screen_type.assistant_tournaments(event)
        ]
        if answers.get('paged') == 'menu':
            lines.append(
                _('A “{name}” screen for {tournament}, over several pages.').format(
                    name=goal.short_name,
                    tournament=tournament_names(tournament_ids[:1]),
                )
            )
            menu_line = _('A menu named “{name}” to pick the page.')
        elif answers.get('nav') == 'single' or len(tournament_ids) == 1:
            lines.append(
                _('A “{name}” screen covering {tournaments}.').format(
                    name=goal.short_name,
                    tournaments=tournament_names(tournament_ids),
                )
            )
        else:
            lines.append(
                _('One “{name}” screen per tournament: {tournaments}.').format(
                    name=goal.short_name,
                    tournaments=tournament_names(tournament_ids),
                )
            )
            menu_line = _(
                'A menu named “{name}” for the players to pick their tournament.'
            )
    elif answers.get('paged'):
        tournament_id: int = (
            answers.get('paged_tournament')
            or screen_type.assistant_tournaments(event)[0].id
        )
        lines.append(
            _('A “{name}” screen for {tournament}, over several pages.').format(
                name=goal.short_name,
                tournament=tournament_names([tournament_id]),
            )
        )
        if answers.get('paged_nav') == 'menu':
            menu_line = _('A menu named “{name}” to pick the page.')
    else:
        lines.append(
            _('A “{name}” screen covering {tournaments}.').format(
                name=goal.short_name,
                tournaments=tournament_names(
                    answers.get('switch_tournaments')
                    or [
                        tournament.id
                        for tournament in screen_type.assistant_tournaments(event)
                    ]
                ),
            )
        )
    if menu_line is not None:
        lines.append(menu_line.format(name=_assistant_menu_name(event, goal)))
    channel_answer = answers.get('channel')
    if channel_answer == 'new':
        lines.append(
            _('A new channel named “{name}”, with everything designed for it.').format(
                name=answers.get('channel_name') or ''
            )
        )
    elif isinstance(channel_answer, int):
        lines.append(
            _('Everything is marked as designed for the channel “{name}”.').format(
                name=event.display_controllers_by_id[channel_answer].name
            )
        )
    return lines
