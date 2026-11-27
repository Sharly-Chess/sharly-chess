"""The screen setup assistant: a guided, full-page flow that creates in one
go a screen (or several screens behind a menu, or a paged screen), and if
wanted the channel it is designed for.

The assistant starts from a goal (what to put up, see ``AssistantGoal``).
Each goal leads into the questions of its screen type
(``ScreenType.assistant_questions()``), which end on the shared channel
questions built here. The answers are read back with ``data.wizard.Wizard``
and turned into stored objects by ``create_from_assistant()``."""

from dataclasses import dataclass, field, replace
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
    StoredRotatingScreen,
    StoredRotator,
)
from utils import Utils

if TYPE_CHECKING:
    from data.event import Event
    from data.screens.display_controller import DisplayController
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
        _('The players checked in and those not yet checked in.'),
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
        _('The ranking, the cross-table or, for the round robins, the grid.'),
        'bi-trophy',
        _('Standings'),
    )
    return goals


def assistant_other_type_names(event: Event) -> list[str]:
    """The names of the screen types the assistant has no goal for (plugin
    types included), to point at the standard forms."""
    covered = {
        type_id
        for goal in assistant_goals(event)
        for type_id in goal.screen_type.assistant_covered_type_ids(event)
    }
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


def channel_switch_question_id(channel_id: int) -> str:
    """The ID of the question asking whether the existing channel
    *channel_id* is switched to what is created."""
    return f'channel_switch_{channel_id}'


def assistant_created_kind(
    event: Event, goal: AssistantGoal, answers: dict[str, Any]
) -> str:
    """What a channel switched to what is created shows (see
    ``_AssistantWriter._show_on()``): ``menu`` when a menu is created,
    ``rotator`` when a rotator is, ``screen`` otherwise (a screen or a paged
    screen)."""
    if goal.accepts_input:
        tournament_ids: list[int] = answers.get('tournaments') or [
            tournament.id
            for tournament in goal.screen_type.assistant_tournaments(event)
        ]
        if answers.get('paged') == 'menu':
            return 'menu'
        if answers.get('nav') == 'single' or len(tournament_ids) == 1:
            return 'screen'
        return 'menu'
    if split := _grid_split(goal, answers):
        return 'rotator' if split == 'rotate' else 'menu'
    if answers.get('paged') and answers.get('paged_nav') == 'menu':
        return 'menu'
    return 'screen'


def channel_switch_yes_text(kind: str) -> str:
    """The answer switching an existing channel to what is created, of the
    *kind* given by ``assistant_created_kind()``."""
    return {
        'menu': _('Yes, show the new menu on this channel'),
        'rotator': _('Yes, show the new rotator on this channel'),
        'screen': _('Yes, show the new screen on this channel'),
    }[kind]


def channel_switch_question_text(channel_name: str, kind: str) -> str:
    """The question asking whether the existing channel *channel_name* is
    switched to what is created, of the *kind* given by
    ``assistant_created_kind()``."""
    return {
        'menu': _('Do you want the channel “{channel}” to show the new menu?'),
        'rotator': _('Do you want the channel “{channel}” to show the new rotator?'),
        'screen': _('Do you want the channel “{channel}” to show the new screen?'),
    }[kind].format(channel=channel_name)


def _channel_switch_question(
    event: Event, goal: AssistantGoal, channel: DisplayController
) -> WizardRadioQuestion:
    """Whether the existing *channel*, picked for the screen, is switched to
    what is created, saying what it shows now. Switched by default only when
    it shows nothing (not to take a display away from what it shows). The
    question and the answer switching it name the menu, the rotator or the
    screen created, once the answers before are known."""

    def kind(answers: dict[str, Any]) -> str:
        return assistant_created_kind(event, goal, answers)

    shown_name = channel.assigned_name if channel.assigned_object is not None else None
    if shown_name is not None:
        help_text = _('The channel “{channel}” currently shows “{shown}”.').format(
            channel=channel.name, shown=shown_name
        )
        keep_text = _('No, keep showing “{shown}”').format(shown=shown_name)
    else:
        help_text = _('The channel “{channel}” currently shows nothing.').format(
            channel=channel.name
        )
        keep_text = _('No, keep showing nothing')
    return WizardRadioQuestion(
        stage='channel',
        text=channel_switch_question_text(channel.name, 'screen'),
        text_for_answers=lambda answers: channel_switch_question_text(
            channel.name, kind(answers)
        ),
        help=help_text,
        options=[
            WizardOption(
                value=True,
                text=channel_switch_yes_text('screen'),
                text_for_answers=lambda answers: channel_switch_yes_text(kind(answers)),
                summary=_('Shown on the channel'),
            ),
            WizardOption(
                value=False,
                text=keep_text,
                summary=_('Not shown on the channel'),
            ),
        ],
        default_value=shown_name is None,
    )


def _channel_questions(event: Event, goal: AssistantGoal) -> dict[str, WizardQuestion]:
    """The questions ending every assistant chain: the channel the screen is
    for ('channel'), whether an existing channel picked is switched to what
    is created (see channel_switch_question_id()), and the name of a
    channel created on the way ('channel_name')."""
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
                next=channel_switch_question_id(channel.id),
            )
            for channel in channels
        )
        options.append(
            WizardOption(
                value='new',
                text=_('A new channel'),
                help=_(
                    'The screen is marked as designed for this new channel, '
                    'which shows it.'
                ),
                next='channel_name',
            )
        )
        options.append(
            WizardOption(
                value=None,
                text=_('No channel'),
                help=_('You will need to select the screen on your display.'),
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
                help=_(
                    'The screen is marked as designed for this new channel, '
                    'which shows it.'
                ),
                next='channel_name',
            ),
            WizardOption(
                value=None,
                text=_('No channel — just create the screen'),
                help=_('You will need to select the screen on your display.'),
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
    } | {
        channel_switch_question_id(channel.id): _channel_switch_question(
            event, goal, channel
        )
        for channel in channels
    }


def assistant_wizard(event: Event, goal: AssistantGoal) -> Wizard:
    """The questions the assistant asks for *goal*: those of its screen
    type, ending on the channel questions."""
    questions = goal.screen_type.assistant_questions(event, goal.accepts_input)
    assert questions is not None
    return Wizard(
        title=goal.title,
        questions={**questions, **_channel_questions(event, goal)},
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
    # The types of the screens created (a standings goal can create a
    # round-robin grid)
    screen_type_ids: set[str] = field(default_factory=set)
    family_ids: list[int] = field(default_factory=list)
    # The name of the menu created, if any
    menu_name: str | None = None
    # The ID of that menu, to scroll to it
    menu_id: int | None = None
    # The name and ID of the rotator created, if any
    rotator_name: str | None = None
    rotator_id: int | None = None
    # The name of the channel the screens were designed for (created or not)
    channel_name: str | None = None
    # Whether the channel was created by the assistant
    channel_created: bool = False
    # The ID of the existing channel switched to what was created, if any
    # (its display is told to show it)
    channel_switched_id: int | None = None


def _assistant_menu_name(
    event: Event, goal: AssistantGoal, base_name: str | None = None
) -> str:
    """The name of a menu the assistant creates for *goal*: named after the
    goal rather than the screen type (a result entry menu holds boards
    screens), or after *base_name*, with a number when the name is taken."""
    return Utils.get_unused_item_name(
        base_name or goal.short_name, [menu.name for menu in event.sorted_menus]
    )


def _assistant_rotator_name(event: Event, base_name: str) -> str:
    """The name of a rotator the assistant creates, with a number when the
    name is taken."""
    return Utils.get_unused_item_name(
        base_name, [rotator.name for rotator in event.sorted_rotators]
    )


def _grid_split(goal: AssistantGoal, answers: dict[str, Any]) -> str | None:
    """How the round-robin grids of a standings goal are split: ``rotate``
    or ``menu`` for a page per grid, None for a single page (or when no
    grid is asked for)."""
    if answers.get('ranking_kind') != 'grid':
        return None
    if len(answers.get('grid_tournaments') or []) < 2:
        return None
    split = answers.get('grid_split')
    return split if split in ('rotate', 'menu') else None


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
        self._rotator_id: int | None = None
        self._used_uniq_ids: set[str] = set()

    def write(self) -> AssistantCreation:
        if self.goal.accepts_input:
            self._write_input_screens()
        else:
            self._write_display_screens()
        self._write_channel()
        return self.creation

    def _tournament_uniq_id(
        self, tournament_id: int, used: list[str], type_id: str | None = None
    ) -> str:
        """A screen or family uniq ID named after its tournament (and the
        type *type_id*, the goal's by default), for the screens created
        behind a menu or a rotator."""
        tournament = self.event.tournaments_by_id[tournament_id]
        prefix = type_id or self.goal.screen_type.id
        uniq_id = Utils.get_unused_item_uniq_id(
            f'{prefix}-{Utils.name_to_uniq_id(tournament.name)}',
            used + list(self._used_uniq_ids),
        )
        self._used_uniq_ids.add(uniq_id)
        return uniq_id

    def _add_screen(
        self,
        tournament_ids: list[int],
        uniq_id: str,
        screen_type: ScreenType | None = None,
        **fields: Any,
    ) -> None:
        """A screen with a set for each of *tournament_ids*, of
        *screen_type* (the goal's by default) and its *fields*."""
        stored_screen = self.database.add_stored_screen(
            (screen_type or self.goal.screen_type).assistant_stored_screen(
                self.event,
                self.answers,
                self.goal.accepts_input,
                tournament_ids,
                uniq_id,
                **fields,
            )
        )
        assert stored_screen.id is not None
        for tournament_id in tournament_ids:
            self.database.add_stored_screen_set(stored_screen.id, tournament_id)
        self._screen_ids.append(stored_screen.id)
        self.creation.screen_ids.append(stored_screen.id)
        self.creation.screen_type_ids.add(stored_screen.type)
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
        self.creation.screen_type_ids.add(stored_family.type)
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

    def _add_menu(self, base_name: str | None = None) -> None:
        """A menu pointing to everything created so far."""
        menu_name = _assistant_menu_name(self.event, self.goal, base_name)
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

    def _add_rotator(self, base_name: str) -> None:
        """A rotator showing in turn the screens created so far."""
        rotator_name = _assistant_rotator_name(self.event, base_name)
        self._rotator_id = self.database.add_stored_rotator(
            StoredRotator(id=None, name=rotator_name)
        )
        for index, screen_id in enumerate(self._screen_ids):
            self.database.add_stored_rotating_screen(
                StoredRotatingScreen(
                    id=None,
                    rotator_id=self._rotator_id,
                    screen_id=screen_id,
                    index=index,
                )
            )
        self.creation.rotator_name = rotator_name
        self.creation.rotator_id = self._rotator_id

    def _write_split_grids(self, split: str) -> None:
        """A round-robin grid screen per round robin, shown in turn by a
        rotator or picked in a menu."""
        from data.screens.screen_types import RoundRobinGridScreenType

        grid_type = RoundRobinGridScreenType()
        for tournament_id in self.answers['grid_tournaments']:
            self._add_screen(
                [tournament_id],
                self._tournament_uniq_id(
                    tournament_id,
                    list(self.event.basic_screens_by_uniq_id),
                    grid_type.id,
                ),
                grid_type,
                round_robin_grid_by_rank=bool(self.answers.get('grid_order')),
                round_robin_grid_players=False,
            )
        if split == 'rotate':
            self._add_rotator(_('Round-robin grids'))
        else:
            self._add_menu(_('Round-robin grids'))

    def _write_display_screens(self) -> None:
        if split := _grid_split(self.goal, self.answers):
            self._write_split_grids(split)
            return
        stored = self.goal.screen_type.create_from_assistant_answers(
            self.event, self.answers, self.goal.accepts_input
        )
        if isinstance(stored, StoredFamily):
            stored_family = self.database.add_stored_family(stored)
            assert stored_family.id is not None
            self._family_ids.append(stored_family.id)
            self.creation.family_ids.append(stored_family.id)
            self.creation.screen_type_ids.add(stored_family.type)
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
            self.creation.screen_type_ids.add(stored_screen.type)
            self.creation.screen_uniq_ids.append(stored_screen.uniq_id)

    def _write_channel(self) -> None:
        channel_answer = self.answers.get('channel')
        stored_channel: StoredDisplayController | None = None
        if channel_answer == 'new':
            # A new channel shows what was created right away (see
            # _show_on()); an existing channel only when asked.
            stored_channel = StoredDisplayController(
                id=None, name=self.answers['channel_name']
            )
            self._show_on(stored_channel)
            stored_channel = self.database.add_stored_display_controller(stored_channel)
            self.creation.channel_created = True
        elif isinstance(channel_answer, int):
            stored_channel = self.event.display_controllers_by_id[
                channel_answer
            ].stored_display_controller
            if self.answers.get(channel_switch_question_id(channel_answer)):
                # Asked for, an existing channel shows what was created too.
                stored_channel = replace(stored_channel)
                self._show_on(stored_channel)
                stored_channel = self.database.update_stored_display_controller(
                    stored_channel
                )
                self.creation.channel_switched_id = channel_answer
        if stored_channel is None:
            return
        assert stored_channel.id is not None
        self.creation.channel_name = stored_channel.name
        # What was created is designed for the channel: the menu or the
        # rotator when there is one, the screens and paged screens
        # otherwise.
        if self._menu_id is not None:
            self.database.set_stored_menu_display_controllers(
                self._menu_id, [stored_channel.id]
            )
            return
        if self._rotator_id is not None:
            self.database.set_stored_rotator_display_controllers(
                self._rotator_id, [stored_channel.id]
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

    def _show_on(self, stored_channel: StoredDisplayController) -> None:
        """Set *stored_channel* to show what was created: the menu or the
        rotator when there is one, else the paged screen or the screen
        created (the assistant creates only one of them when there is no
        menu nor rotator)."""
        stored_channel.screen_id = None
        stored_channel.rotator_id = None
        stored_channel.family_id = None
        stored_channel.family_page = None
        stored_channel.menu_id = None
        if self._menu_id is not None:
            stored_channel.menu_id = self._menu_id
        elif self._rotator_id is not None:
            stored_channel.rotator_id = self._rotator_id
        elif self._family_ids:
            stored_channel.family_id = self._family_ids[0]
        elif self._screen_ids:
            stored_channel.screen_id = self._screen_ids[0]


def create_from_assistant(
    event: Event,
    goal: AssistantGoal,
    answers: dict[str, Any],
) -> AssistantCreation:
    """Create the screens, the paged screens, the menu and the channel the
    assistant *answers* describe, in one database write. What was created is
    marked as designed for the channel picked or created; a channel created
    also shows it, a channel picked only when the answers ask for it."""
    with EventDatabase(event.uniq_id, write=True) as database:
        return _AssistantWriter(event, goal, answers, database).write()


def assistant_summary(
    event: Event,
    goal: AssistantGoal,
    answers: dict[str, Any],
) -> list[str]:
    """The actions the assistant is about to perform, one line each, shown
    before the Create button (mirrors ``create_from_assistant()``)."""
    # The standings goal names what it shows: the ranking, the cross-table
    # or the round-robin grid.
    item_name = {
        'crosstable': _('Cross-table'),
        'grid': _('Round-robin grid'),
    }.get(answers.get('ranking_kind', ''), goal.short_name)
    screen_type = goal.screen_type
    shown_type: ScreenType = screen_type
    if answers.get('ranking_kind') == 'grid':
        from data.screens.screen_types import RoundRobinGridScreenType

        shown_type = RoundRobinGridScreenType()
    lines: list[str] = []
    menu_line: str | None = None
    menu_base_name: str | None = None

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
                _(
                    'Create a “{name}” screen for {tournament}, over several pages.'
                ).format(
                    name=goal.short_name,
                    tournament=tournament_names(tournament_ids[:1]),
                )
            )
            menu_line = _('Create a menu named “{name}” to pick the page.')
        elif answers.get('nav') == 'single' or len(tournament_ids) == 1:
            lines.append(
                _('Create a “{name}” screen for tournaments {tournaments}.').format(
                    name=goal.short_name,
                    tournaments=tournament_names(tournament_ids),
                )
            )
        else:
            lines.append(
                _('Create one “{name}” screen per tournament: {tournaments}.').format(
                    name=goal.short_name,
                    tournaments=tournament_names(tournament_ids),
                )
            )
            menu_line = _(
                'Create a menu named “{name}” for the players to pick their tournament.'
            )
    elif split := _grid_split(goal, answers):
        lines.append(
            _('Create one “{name}” screen per tournament: {tournaments}.').format(
                name=item_name,
                tournaments=tournament_names(answers['grid_tournaments']),
            )
        )
        if split == 'rotate':
            lines.append(
                _('Create a rotator named “{name}” showing them in turn.').format(
                    name=_assistant_rotator_name(event, _('Round-robin grids'))
                )
            )
        else:
            menu_line = _('Create a menu named “{name}” to pick the grid.')
            menu_base_name = _('Round-robin grids')
    elif answers.get('paged'):
        tournament_id: int = (
            answers.get('paged_tournament')
            or screen_type.assistant_tournaments(event)[0].id
        )
        lines.append(
            _('Create a “{name}” screen for {tournament}, over several pages.').format(
                name=item_name,
                tournament=tournament_names([tournament_id]),
            )
        )
        if answers.get('paged_nav') == 'menu':
            menu_line = _('Create a menu named “{name}” to pick the page.')
    else:
        lines.append(
            _('Create a “{name}” screen for tournaments {tournaments}.').format(
                name=item_name,
                tournaments=tournament_names(
                    answers.get('grid_tournaments')
                    or answers.get('switch_tournaments')
                    or [
                        tournament.id
                        for tournament in shown_type.assistant_tournaments(event)
                    ]
                ),
            )
        )
    if menu_line is not None:
        lines.append(
            menu_line.format(name=_assistant_menu_name(event, goal, menu_base_name))
        )
    channel_answer = answers.get('channel')
    channel_name: str | None = None
    if channel_answer == 'new':
        channel_name = answers.get('channel_name') or ''
    elif isinstance(channel_answer, int):
        channel_name = event.display_controllers_by_id[channel_answer].name
    if channel_name is not None:
        # The last line is what the channel is designed for: the menu or the
        # rotator when there is one, else the screen.
        lines[-1] = _(
            '{item} and mark it as designed for the channel “{name}”.'
        ).format(item=lines[-1].rstrip('.'), name=channel_name)
        # What the channel shows when it is switched to what is created.
        shown_kind = assistant_created_kind(event, goal, answers)
        if channel_answer == 'new':
            lines.insert(
                0, _('Create a new channel named “{name}”.').format(name=channel_name)
            )
            shown_name: str | None = None
        elif isinstance(channel_answer, int) and answers.get(
            channel_switch_question_id(channel_answer)
        ):
            channel = event.display_controllers_by_id[channel_answer]
            shown_name = (
                channel.assigned_name if channel.assigned_object is not None else None
            )
        else:
            return lines
        # The channel is switched to what is created: a line of its own.
        if shown_name is None:
            show_line = {
                'menu': _('Show the new menu on the channel “{channel}”.'),
                'rotator': _('Show the new rotator on the channel “{channel}”.'),
                'screen': _('Show the new screen on the channel “{channel}”.'),
            }[shown_kind]
        else:
            show_line = {
                'menu': _(
                    'Show the new menu on the channel “{channel}” instead of “{shown}”.'
                ),
                'rotator': _(
                    'Show the new rotator on the channel “{channel}” instead of '
                    '“{shown}”.'
                ),
                'screen': _(
                    'Show the new screen on the channel “{channel}” instead of '
                    '“{shown}”.'
                ),
            }[shown_kind]
        lines.append(show_line.format(channel=channel_name, shown=shown_name))
    return lines
