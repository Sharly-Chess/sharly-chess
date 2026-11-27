"""Wizards: questions asked one after the other, the answers leading from a
question to the next one (used by the screen setup assistant, see
``data/screens/assistant.py``).

Each kind of question is a subclass of ``WizardQuestion``, whose ``type``
names the template showing it
(``admin/wizard_questions/<type>.html``)."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, override

from common.i18n import _

if TYPE_CHECKING:
    from data.tournament import Tournament


@dataclass
class WizardOption:
    # The value returned if this choice is selected
    value: Any
    # The text that corresponds to the option
    text: str
    # An optional help text to describe the option
    help: str | None = None
    # The ID of the next question (if None see the next question of the question itself)
    next: str | None = None
    # The answer as listed among those given, when the text alone would not
    # say what it answers (a bare "Yes"); the text if None
    summary: str | None = None
    # The text from the answers given before, when it depends on them: the
    # page asks the server for it when the question is shown, ``text``
    # standing until then
    text_for_answers: Callable[[dict[str, Any]], str] | None = None


@dataclass
class WizardQuestion(ABC):
    # The kind of question (set by each subclass), naming its template
    type: ClassVar[str]

    # The text of the question
    text: str
    # An optional help text to precise the question
    help: str | None = None
    # The value set by default
    default_value: Any | None = None
    # True if the question is omitted
    disabled: bool = False
    # The ID of the next question (if None it is the end of the wizard)
    next: str | None = None
    # The stage of the wizard the question belongs to (see Wizard.stages)
    stage: str = 'layout'
    # The answer as listed among those given, ``{answer}`` standing for it,
    # when the bare answer would not say what it answers (a number of
    # pages); the bare answer if None
    summary: str | None = None
    # The text from the answers given before, when it depends on them (see
    # WizardOption.text_for_answers)
    text_for_answers: Callable[[dict[str, Any]], str] | None = None

    @abstractmethod
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        """The answer read from the form value *raw* (stripped), see
        read_answer()."""

    def read_answer(self, raw: str) -> tuple[Any, str | None]:
        """The answer read from the form value *raw* and the ID of the next
        question (None when the question is the last one). Raises
        ValueError with the message to show when *raw* is not a valid
        answer."""
        return self._read_answer(raw.strip())

    @property
    def default_form_value(self) -> str:
        """The default value (``default_value``) as set in the form field."""
        return '' if self.default_value is None else str(self.default_value)

    @property
    def required_text(self) -> str:
        """The message shown when the question is left unanswered."""
        return _('Please answer the question.')


@dataclass
class WizardChoiceQuestion(WizardQuestion, ABC):
    """A question answered by choosing among options."""

    # The options to choose from
    options: list[WizardOption] = field(default_factory=list)

    @property
    def select_options(self) -> dict[str, str]:
        """The options, as those of a select (the texts by form value)."""
        return {str(option.value): option.text for option in self.options}


@dataclass
class WizardRadioQuestion(WizardChoiceQuestion):
    """The options are presented as radio buttons, the form value being the
    index of the option chosen."""

    type: ClassVar[str] = 'radio'

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        try:
            option = self.options[int(raw)]
        except ValueError, IndexError:
            raise ValueError(_('Please choose an answer.')) from None
        return option.value, option.next or self.next

    @property
    @override
    def default_form_value(self) -> str:
        """The index of the option whose value is the default value (the
        first option if none)."""
        value = self.default_value
        for index, option in enumerate(self.options):
            # Typed comparison: False must not select an option 0.
            if type(option.value) is type(value) and option.value == value:
                return str(index)
        return '0' if self.options else ''


@dataclass
class WizardStrQuestion(WizardQuestion):
    type: ClassVar[str] = 'str'

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        return raw or None, self.next


@dataclass
class WizardNameQuestion(WizardStrQuestion):
    """A required name, refused when already used."""

    # The names already taken
    used_names: Collection[str] = ()

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        if not raw:
            raise ValueError(_('This field is required.'))
        if raw in self.used_names:
            raise ValueError(_('This name is already used.'))
        return raw, self.next


@dataclass
class WizardIntQuestion(WizardQuestion):
    type: ClassVar[str] = 'int'

    # The minimum value
    min: int | None = None

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(_('An integer is expected.')) from None
        if self.min is not None and value < self.min:
            raise ValueError(
                _('The value must be at least {min}.').format(min=self.min)
            )
        return value, self.next


@dataclass
class WizardBoolQuestion(WizardQuestion):
    type: ClassVar[str] = 'bool'

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        return raw.lower() in ('on', 'true', '1'), self.next

    @property
    @override
    def default_form_value(self) -> str:
        return 'on' if self.default_value else ''


def _tournament_options(tournaments: Iterable[Tournament]) -> list[WizardOption]:
    return [
        WizardOption(value=tournament.id, text=tournament.name)
        for tournament in tournaments
    ]


class WizardTournamentQuestion(WizardChoiceQuestion):
    """One of *tournaments*, the first one by default. The other arguments
    are those of WizardQuestion (*text* defaulting to a generic one)."""

    type: ClassVar[str] = 'tournament'

    def __init__(
        self,
        tournaments: Iterable[Tournament],
        text: str | None = None,
        **kwargs: Any,
    ):
        options = _tournament_options(tournaments)
        kwargs.setdefault('default_value', options[0].value if options else None)
        super().__init__(
            text=text or _('Select the tournament:'), options=options, **kwargs
        )

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        try:
            tournament_id = int(raw)
        except ValueError:
            tournament_id = 0
        if tournament_id not in [option.value for option in self.options]:
            raise ValueError(_('Please choose the tournament.'))
        return tournament_id, self.next


class WizardTournamentsQuestion(WizardChoiceQuestion):
    """Some of *tournaments*, all by default, at least *min_count* of them.
    When *next_single* is given it is the next question when a single
    tournament is chosen, ``next`` leading on from a choice of several. The
    other arguments are those of WizardQuestion (*text* defaulting to a
    generic one)."""

    type: ClassVar[str] = 'tournaments'

    def __init__(
        self,
        tournaments: Iterable[Tournament],
        text: str | None = None,
        next_single: str | None = None,
        min_count: int = 1,
        **kwargs: Any,
    ):
        options = _tournament_options(tournaments)
        kwargs.setdefault('default_value', [option.value for option in options])
        super().__init__(
            text=text or _('Select the tournaments:'), options=options, **kwargs
        )
        self.next_single = next_single
        self.min_count = min_count

    @property
    @override
    def required_text(self) -> str:
        if self.min_count > 1:
            return _('Please choose at least {count} tournaments.').format(
                count=self.min_count
            )
        return super().required_text

    @override
    def _read_answer(self, raw: str) -> tuple[Any, str | None]:
        allowed_tournament_ids = [option.value for option in self.options]
        try:
            tournament_ids = list(
                dict.fromkeys(int(item) for item in raw.split(';') if item)
            )
        except ValueError:
            tournament_ids = []
        if not tournament_ids or any(
            tournament_id not in allowed_tournament_ids
            for tournament_id in tournament_ids
        ):
            raise ValueError(_('Please choose the tournaments.'))
        if len(tournament_ids) < self.min_count:
            raise ValueError(self.required_text)
        next_question_id = (
            self.next_single
            if len(tournament_ids) == 1 and self.next_single is not None
            else self.next
        )
        return tournament_ids, next_question_id

    @property
    @override
    def default_form_value(self) -> str:
        """The IDs of the tournaments, separated by semicolons."""
        return ';'.join(
            str(tournament_id) for tournament_id in self.default_value or []
        )


@dataclass
class Wizard:
    """A complete wizard."""

    # The title of the wizard
    title: str
    # The questions asked, the first one first
    questions: dict[str, WizardQuestion]

    @property
    def first_question_id(self) -> str | None:
        """The ID of the first question asked (disabled questions skipped)."""
        return self.enabled_question_id(next(iter(self.questions), None))

    def enabled_question_id(self, question_id: str | None) -> str | None:
        """The ID of the question asked when *question_id* comes next: the
        question itself, or the first of its successors that is not
        disabled. None when there is none (the wizard ends)."""
        while question_id is not None and self.questions[question_id].disabled:
            question_id = self.questions[question_id].next
        return question_id

    @staticmethod
    def answer_field(question_id: str) -> str:
        """The name of the form field holding the answer to a question."""
        return f'answer_{question_id}'

    @property
    def default_data(self) -> dict[str, str]:
        """The form data holding the default values of the questions."""
        return {
            self.answer_field(question_id): question.default_form_value
            for question_id, question in self.questions.items()
            if not question.disabled
        }

    def read_answers(
        self, data: dict[str, str]
    ) -> tuple[dict[str, Any], list[str], dict[str, str]]:
        """Read the answers from the form *data*, following the questions
        from the first one as the answers lead. Returns the answers by
        question ID, the IDs of the questions asked (in order) and the
        errors by form field (reading stops at the first error)."""
        answers: dict[str, Any] = {}
        path: list[str] = []
        errors: dict[str, str] = {}
        question_id = self.first_question_id
        while question_id is not None:
            if question_id in path:
                raise RuntimeError(f'Wizard loop on question [{question_id}].')
            path.append(question_id)
            field_name = self.answer_field(question_id)
            try:
                answers[question_id], next_question_id = self.questions[
                    question_id
                ].read_answer(data.get(field_name, ''))
            except ValueError as error:
                errors[field_name] = str(error)
                break
            if next_question_id is not None and next_question_id not in self.questions:
                raise RuntimeError(f'Unknown wizard question [{next_question_id}].')
            question_id = self.enabled_question_id(next_question_id)
        return answers, path, errors
