import copy
from functools import partial
from typing import Any, Annotated


from data.criteria.player_filter_options import (
    MinRatingOption,
    MaxRatingOption,
    GenderOption,
    MinAgeCategoryOption,
    MaxAgeCategoryOption,
)
from data.loader import Event
from litestar import get, post, patch, delete
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.exception import OptionError
from common.i18n import _
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.player_categories import NoCategory, PlayerCategory
from data.print_documents.documents import (
    PrizeAssignmentPrintDocument,
    PrizeListPrintDocument,
)
from data.prize.managers import PrizeSharingManager, PrizeTypeManager
from data.criteria.managers import PrizePlayerFilterManager, PlayerFilterOptionManager
from data.criteria.player_filters import (
    PlayerFilter,
    RatingPlayerFilter,
    AgePlayerFilter,
    GenderPlayerFilter,
)
from data.prize.prize import Prize
from data.prize.prize_category import PrizeCategory
from data.prize.prize_criterion import PrizeCriterion
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import NoPrizeSharing, AveragePrizeSharing
from data.prize.prize_type import MonetaryPrizeType
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPrizeGroup,
    StoredPrizeCategory,
    StoredPrize,
    StoredPrizeCriterion,
)
from utils import Utils
from utils.enum import FormAction, PlayerGender
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, TournamentActionGuard
from web.messages import Message
from web.session import (
    SessionPrizesAddOtherActive,
    SessionPrizeCategoriesAddOtherActive,
    SessionPrizeCriteriaAddOtherActive,
    SessionPrizesShowDetails,
)
from web.utils import SelectOption

logger = get_logger()


class PrizeAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        prize_group_id: int | None = None,
        prize_category_id: int | None = None,
        prize_criterion_id: int | None = None,
        prize_id: int | None = None,
    ):
        super().__init__(request)
        self.admin_tournament: Tournament | None = None
        self.admin_prize_group: PrizeGroup | None = None
        self.admin_prize_category: PrizeCategory | None = None
        self.admin_prize_criterion: PrizeCriterion | None = None
        self.admin_prize: Prize | None = None
        self.show_details = SessionPrizesShowDetails(request).get()
        self.allowed_tournaments = self.client.allowed_tournaments_for_action(
            AuthAction.VIEW_PRIZES_TAB
        )

        event = self.get_admin_event()
        if tournament_id:
            if tournament_id not in event.tournaments_by_id:
                raise NotFoundException(
                    f'Unknown tournament ID [{tournament_id}] '
                    f'for event [{event.uniq_id}]'
                )
            self.admin_tournament = event.tournaments_by_id[tournament_id]
        elif self.allowed_tournaments:
            self.admin_tournament = self.allowed_tournaments[0]

        if prize_group_id:
            tournament = self.get_admin_tournament()
            if prize_group_id not in tournament.prize_groups_by_id:
                raise NotFoundException(
                    f'Unknown prize group ID [{prize_group_id}] for '
                    f'tournament [{tournament_id}] of event [{event.uniq_id}]'
                )
            self.admin_prize_group = tournament.prize_groups_by_id[prize_group_id]
        else:
            self.set_default_prize_group()

        if prize_category_id:
            prize_group = self.get_admin_prize_group()
            if prize_category_id not in prize_group.categories_by_id:
                raise NotFoundException(
                    f'Unknown category ID [{prize_category_id}] for '
                    f'prize group [{prize_group_id}]'
                )
            self.admin_prize_category = prize_group.categories_by_id[prize_category_id]

        if prize_criterion_id:
            prize_category = self.get_admin_prize_category()
            if prize_criterion_id not in prize_category.criteria_by_id:
                raise NotFoundException(
                    f'Unknown criterion ID [{prize_criterion_id}] for '
                    f'prize category [{prize_category_id}]'
                )
            self.admin_prize_criterion = prize_category.criteria_by_id[
                prize_criterion_id
            ]

        if prize_id:
            prize_category = self.get_admin_prize_category()
            if prize_id not in prize_category.prizes_by_id:
                raise NotFoundException(
                    f'Unknown prize ID [{prize_id}] for '
                    f'prize category [{prize_category_id}]'
                )
            self.admin_prize = prize_category.prizes_by_id[prize_id]

    def set_default_prize_group(self):
        if self.admin_tournament and self.admin_tournament.prize_groups:
            self.admin_prize_group = self.admin_tournament.sorted_prize_groups[0]
        else:
            self.admin_prize_group = None

    @property
    def template_context(self) -> dict[str, Any]:
        prize_currency = self.get_admin_event().prize_currency
        return super().template_context | {
            'admin_event_tab': 'admin-event-prizes-tab',
            'admin_tournament': self.admin_tournament,
            'admin_prize_group': self.admin_prize_group,
            'admin_prize_category': self.admin_prize_category,
            'admin_prize_criterion': self.admin_prize_criterion,
            'admin_prize': self.admin_prize,
            'ordinal_integer': Utils.ordinal_integer,
            'format_prize_value': partial(
                Utils.currency_value_str,
                currency=prize_currency,
            ),
            'prize_currency': prize_currency,
            'tournament_options': self.get_tournament_options(self.allowed_tournaments),
            'prize_group_options': self.get_prize_group_options(),
            'show_details': self.show_details,
            'default_print_document': PrizeAssignmentPrintDocument.static_id()
            if self.admin_tournament and self.admin_tournament.finished
            else PrizeListPrintDocument.static_id(),
        }

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_prize_group(self) -> PrizeGroup:
        assert self.admin_prize_group is not None
        return self.admin_prize_group

    def get_admin_prize_category(self) -> PrizeCategory:
        assert self.admin_prize_category is not None
        return self.admin_prize_category

    def get_admin_prize_criterion(self) -> PrizeCriterion:
        assert self.admin_prize_criterion is not None
        return self.admin_prize_criterion

    def get_admin_prize(self) -> Prize:
        assert self.admin_prize is not None
        return self.admin_prize

    def get_prize_group_options(self) -> dict[str, str]:
        if not self.admin_tournament:
            return {}
        return {
            self.value_to_form_data(prize_group.id): prize_group.name
            for prize_group in self.admin_tournament.sorted_prize_groups
        }


class PrizeAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        TournamentActionGuard(AuthAction.VIEW_PRIZES_TAB),
    ]
    manage_guards = [TournamentActionGuard(AuthAction.MANAGE_PRIZES)]

    @classmethod
    def _admin_event_prizes_render(
        cls,
        web_context: PrizeAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {}),
        )

    @get(
        path=[
            '/event/{event_uniq_id:str}/prizes',
            '/event/{event_uniq_id:str}/prizes/{tournament_id:int}',
            '/event/{event_uniq_id:str}/prizes/{tournament_id:int}/{prize_group_id:int}',
        ],
        name='admin-event-prizes-tab',
    )
    async def htmx_admin_prizes_tab(
        self,
        request: HTMXRequest,
        tournament_id: int | None,
        prize_group_id: int | None,
        show_details: bool | None,
    ) -> Template:
        if show_details is not None:
            SessionPrizesShowDetails(request).set(show_details)
        web_context = PrizeAdminWebContext(request, tournament_id)

        if prize_group_id:
            tournament = web_context.get_admin_tournament()
            if prize_group_id in tournament.prize_groups_by_id:
                web_context.admin_prize_group = tournament.prize_groups_by_id[
                    prize_group_id
                ]
        return self._admin_event_prizes_render(web_context)

    @get(
        path=(
            '/prizes/prize-players-modal/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-players-modal',
    )
    async def htmx_admin_prize_players_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )

        prize_group = web_context.get_admin_prize_group()
        assigned_prizes_by_player_id = {
            assigned_prize.assigned_to.id: assigned_prize
            for assigned_prize in prize_group.assign_prizes()
            if assigned_prize.assigned_to
        }
        return self._admin_event_prizes_render(
            web_context,
            {
                'modal': 'prize_players',
                'assigned_prizes_by_player_id': assigned_prizes_by_player_id,
            },
        )

    # -------------------------------------------------------------------------
    # Prize groups
    # -------------------------------------------------------------------------

    @staticmethod
    def _prize_groups_modal_context(tournament: Tournament) -> dict[str, Any]:
        return {
            'modal': 'prize_groups',
            'prize_group_names': [group.name for group in tournament.prize_groups],
        }

    @post(
        path='/prizes/prize-group/create/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-prize-group-create',
        guards=manage_guards,
    )
    async def htmx_admin_prize_group_create(
        self, request: HTMXRequest, tournament_id: int
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id)

        tournament = web_context.get_admin_tournament()
        first_group = len(tournament.prize_groups) == 0
        if first_group:
            name = _('Main group')
        else:
            name = tournament.get_unused_prize_group_name()
        prize_group = tournament.add_prize_group(
            StoredPrizeGroup(
                id=None,
                tournament_id=tournament.id,
                name=name,
            )
        )
        template_context = {}
        if first_group:
            web_context.admin_prize_group = prize_group
            Message.success(
                request,
                _('Prize group [{prize_group}] successfully created.').format(
                    prize_group=prize_group.name
                ),
            )
        else:
            template_context = self._prize_groups_modal_context(tournament)
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/prizes/prize-group/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-update',
        guards=manage_guards,
    )
    async def htmx_admin_prize_group_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id, prize_group_id)

        tournament = web_context.get_admin_tournament()
        prize_group = web_context.get_admin_prize_group()
        prize_group.stored_prize_group.name = (
            WebContext.form_data_to_str(data, 'name') or ''
        )
        prize_group.update()
        return self._admin_event_prizes_render(
            web_context, self._prize_groups_modal_context(tournament)
        )

    @delete(
        path=(
            '/prizes/prize-group/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-delete',
        guards=manage_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_group_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id, prize_group_id)

        tournament = web_context.get_admin_tournament()
        tournament.delete_prize_group(prize_group_id)
        return self._admin_event_prizes_render(
            web_context, self._prize_groups_modal_context(tournament)
        )

    @get(
        path='/prizes/prize-groups-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-prize-groups-modal',
    )
    async def htmx_admin_prize_groups_modal(
        self, request: HTMXRequest, tournament_id: int
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        return self._admin_event_prizes_render(
            web_context, self._prize_groups_modal_context(tournament)
        )

    @get(
        path=(
            '/prizes/prize-group-modal/delete/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-delete-modal',
    )
    async def htmx_admin_prize_group_delete_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(request, tournament_id, prize_group_id),
            {'modal': 'prize_group_delete'},
        )

    # -------------------------------------------------------------------------
    # Prize categories
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_prize_category_form_data(
        data: dict[str, str],
        action: FormAction,
        prize_group: PrizeGroup,
        prize_category: PrizeCategory | None = None,
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = WebContext.form_data_to_str(data, field := 'name')
        if not name:
            errors[field] = _('This field is required.')
        else:
            used_names = [category.name for category in prize_group.categories]
            if prize_category:
                used_names.remove(prize_category.name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        is_main = WebContext.form_data_to_bool(data, 'is_main')
        share_prizes = WebContext.form_data_to_bool(data, 'share_prizes')
        if not is_main and share_prizes:
            message = 'Prize sharing is only allowed for the main category'
            errors[field] = message
            logger.error(message)
        if share_prizes:
            field = 'prize_sharing'
            prize_sharing_id = WebContext.form_data_to_str(data, field) or ''
            try:
                PrizeSharingManager().get_object(prize_sharing_id)
            except KeyError:
                message = f'Unknown prize sharing ID [{prize_sharing_id}]'
                errors[field] = message
                logger.exception(message)
            field = 'sharing_threshold'
            threshold = WebContext.form_data_to_float(data, field)
            if threshold is not None:
                if threshold < 0:
                    errors[field] = _('A positive value is expected.')
                elif prize_category and prize_category.prizes:
                    min_prize_value = prize_category.sorted_prizes[-1].value
                    if threshold > min_prize_value:
                        errors[field] = _(
                            "The threshold can't be greater than the value "
                            'of the last prize of the category ({value}).'
                        ).format(
                            value=(
                                int(min_prize_value)
                                if min_prize_value.is_integer()
                                else min_prize_value
                            )
                        )
        if action == FormAction.CREATE and not is_main:
            field = 'criterion_rating'
            try:
                min_rating = WebContext.form_data_to_int(
                    data, field + '_min', minimum=0
                )
                max_rating = WebContext.form_data_to_int(
                    data, field + '_max', minimum=0
                )
                if min_rating and max_rating and min_rating >= max_rating:
                    errors[field] = _(
                        'Minimum rating is expected to be lower than the maximum rating.'
                    )
            except ValueError:
                errors[field] = _('Positive values are expected.')
            field = 'criterion_age_category'
            min_category: PlayerCategory | None = None
            max_category: PlayerCategory | None = None
            min_id = WebContext.form_data_to_str(data, field + '_min')
            max_id = WebContext.form_data_to_str(data, field + '_max')
            if min_id and min_id != '__placeholder__':
                min_category = PlayerCategory.from_id(min_id)
            if max_id and max_id != '__placeholder__':
                max_category = PlayerCategory.from_id(max_id)
            if min_category and max_category and min_category > max_category:
                errors[field] = _(
                    'Minimum category is expected to be lower or equal to the maximum category.'
                )
        return errors

    @classmethod
    def _render_prize_category_modal(
        cls,
        web_context: PrizeAdminWebContext,
        action: FormAction,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        previous_category: PrizeCategory | None = None,
    ) -> HTMXTemplate:
        request = web_context.request
        event = web_context.get_admin_event()
        prize_group = web_context.get_admin_prize_group()
        if data is None:
            data = WebContext.values_dict_to_form_data(
                {
                    'name': prize_group.get_unused_category_name(),
                    'is_main': prize_group.tournament.main_prize_category is None,
                    'share_prizes': False,
                    'sharing_threshold': '',
                    'prize_sharing': AveragePrizeSharing.static_id(),
                }
            )
            if action == FormAction.CREATE:
                data |= {
                    'criterion_gender': '',
                    'criterion_age_category_min': '',
                    'criterion_age_category_max': '',
                    'criterion_rating_min': '',
                    'criterion_rating_max': '',
                }
        prize_sharing_options = PrizeSharingManager().options()
        prize_sharing_options.pop(NoPrizeSharing.static_id())
        template_context = {
            'modal': 'prize_category',
            'action': action,
            'prize_sharing_options': prize_sharing_options,
            'age_category_options': {
                category.id: category.name
                for category in event.player_categories
                if category != NoCategory()
            },
            'gender_options': {'': '-'}
            | {
                gender.value: gender.name
                for gender in [PlayerGender.MAN, PlayerGender.WOMAN]
            },
            'previous_category': previous_category,
            'add_other_active': SessionPrizeCategoriesAddOtherActive(request).get(),
            'data': data,
            'errors': errors or {},
        }
        return cls._admin_base_event_render(
            web_context.template_context | template_context
        )

    @post(
        path=(
            '/prizes/prize-category/create/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-category-create',
        guards=manage_guards,
    )
    async def htmx_admin_prize_category_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id, prize_group_id)
        prize_group = web_context.get_admin_prize_group()

        add_other = WebContext.resolve_add_other(
            data, SessionPrizeCategoriesAddOtherActive(request)
        )
        action = FormAction.CREATE
        if errors := self._validate_prize_category_form_data(data, action, prize_group):
            return self._render_prize_category_modal(
                web_context, action=action, data=data, errors=errors
            )
        current_main_category = web_context.get_admin_tournament().main_prize_category
        share_prizes = WebContext.form_data_to_bool(data, 'share_prizes')
        stored_category = StoredPrizeCategory(
            id=None,
            prize_group_id=prize_group.id,
            name=WebContext.form_data_to_str(data, 'name') or '',
            is_main=WebContext.form_data_to_bool(data, 'is_main'),
            sharing_threshold=(
                WebContext.form_data_to_float(data, 'sharing_threshold')
                if share_prizes
                else None
            ),
            prize_sharing=(
                data['prize_sharing'] if share_prizes else NoPrizeSharing.static_id()
            ),
            index=len(prize_group.categories),
        )
        if current_main_category and stored_category.is_main:
            current_stored_category = current_main_category.stored_prize_category
            current_stored_category.is_main = False
            current_stored_category.prize_sharing = NoPrizeSharing().id
            current_stored_category.sharing_threshold = None
            current_main_category.update()
        prize_category = prize_group.add_category(stored_category)

        if not prize_category.is_main:
            filters: list[PlayerFilter] = []
            field = 'criterion_rating'
            min_rating = web_context.form_data_to_int(data, field + '_min')
            max_rating = web_context.form_data_to_int(data, field + '_max')
            if min_rating or max_rating:
                filters.append(
                    RatingPlayerFilter(
                        [
                            MinRatingOption(min_rating),
                            MaxRatingOption(max_rating),
                        ]
                    )
                )
            field = 'criterion_age_category'
            min_category = WebContext.form_data_to_str(data, field + '_min')
            max_category = WebContext.form_data_to_str(data, field + '_max')
            if min_category == '__placeholder__':
                min_category = None
            if max_category == '__placeholder__':
                max_category = None
            if min_category or max_category:
                filters.append(
                    AgePlayerFilter(
                        [
                            MinAgeCategoryOption(min_category),
                            MaxAgeCategoryOption(max_category),
                        ]
                    )
                )
            gender = WebContext.form_data_to_str(data, 'criterion_gender')
            if gender:
                filters.append(GenderPlayerFilter([GenderOption(gender)]))
            for filter_ in filters:
                prize_category.add_criterion(
                    StoredPrizeCriterion(
                        id=None,
                        prize_category_id=prize_category.id,
                        type=filter_.id,
                        options={option.id: option.value for option in filter_.options},
                    )
                )
        if add_other:
            return self._render_prize_category_modal(
                web_context,
                action=FormAction.CREATE,
                errors=errors,
                previous_category=prize_category,
            )
        else:
            Message.success(
                request,
                _('Prize category [{prize_category}] successfully created.').format(
                    prize_category=prize_category.name
                ),
            )
        return self._admin_event_prizes_render(web_context)

    @patch(
        path=(
            '/prizes/prize-category/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-update',
        guards=manage_guards,
    )
    async def htmx_admin_prize_category_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )
        prize_group = web_context.get_admin_prize_group()
        prize_category = web_context.get_admin_prize_category()
        action = FormAction.UPDATE
        if errors := self._validate_prize_category_form_data(
            data, action, prize_group, prize_category
        ):
            return self._render_prize_category_modal(
                web_context, action, data=data, errors=errors
            )
        current_main_category = web_context.get_admin_tournament().main_prize_category
        was_main = prize_category.is_main
        share_prizes = WebContext.form_data_to_bool(data, 'share_prizes')
        stored_category = prize_category.stored_prize_category
        stored_category.name = WebContext.form_data_to_str(data, 'name') or ''
        stored_category.is_main = WebContext.form_data_to_bool(data, 'is_main')
        stored_category.prize_sharing = (
            data['prize_sharing'] if share_prizes else NoPrizeSharing.static_id()
        )
        stored_category.sharing_threshold = (
            WebContext.form_data_to_float(data, 'sharing_threshold')
            if share_prizes
            else None
        )
        prize_category.update()
        if not was_main and prize_category.is_main:
            criteria_ids = list(prize_category.criteria_by_id.keys())
            for criterion_id in criteria_ids:
                prize_category.delete_criterion(criterion_id)
            if current_main_category:
                current_stored_category = current_main_category.stored_prize_category
                current_stored_category.is_main = False
                current_stored_category.prize_sharing = NoPrizeSharing().id
                current_stored_category.sharing_threshold = None
                current_main_category.update()
            prize_category.prize_group.reorder_categories()
        Message.success(
            request,
            _('Prize category [{prize_category}] successfully updated.').format(
                prize_category=prize_category.name
            ),
        )
        return self._admin_event_prizes_render(web_context)

    @delete(
        path=(
            '/prizes/prize-category/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-delete',
        guards=manage_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_category_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )

        prize_group = web_context.get_admin_prize_group()
        prize_category = web_context.get_admin_prize_category()
        prize_group.delete_category(prize_category_id)
        Message.success(
            request,
            _('Prize category [{prize_category}] successfully deleted.').format(
                prize_category=prize_category.name
            ),
        )
        web_context.admin_prize_category = None
        return self._admin_event_prizes_render(web_context)

    @post(
        path=(
            '/prizes/prize-category/duplicate/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-duplicate',
        guards=manage_guards,
    )
    async def htmx_admin_prize_category_duplicate(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )

        prize_group = web_context.get_admin_prize_group()
        copy_category = web_context.get_admin_prize_category()
        stored_category = copy.deepcopy(copy_category.stored_prize_category)
        stored_category.name = prize_group.get_unused_category_name(copy_category.name)
        stored_category.index = len(prize_group.categories)
        stored_category.stored_prizes = []
        stored_category.stored_prize_criteria = []
        prize_category = prize_group.add_category(stored_category)
        for prize in copy_category.prizes:
            stored_prize = copy.deepcopy(prize.stored_prize)
            stored_prize.prize_category_id = prize_category.id
            prize_category.add_prize(stored_prize)
        for criterion in copy_category.criteria:
            stored_criterion = copy.deepcopy(criterion.stored_prize_criterion)
            stored_criterion.prize_category_id = prize_category.id
            prize_category.add_criterion(stored_criterion)
        Message.success(
            request,
            _('Prize category [{prize_category}] has been duplicated.').format(
                prize_category=prize_category.name,
            ),
        )
        return self._admin_event_prizes_render(web_context)

    @patch(
        path=(
            '/prizes/prize-category/reorder/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prizes-reorder-categories',
        guards=manage_guards,
    )
    async def htmx_admin_prize_reorder_categories(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id, prize_group_id)

        prize_group = web_context.get_admin_prize_group()
        prize_group.reorder_categories(data['item'])
        return self._admin_event_prizes_render(web_context)

    @get(
        path=(
            '/prizes/prize-category-modal/create/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-category-create-modal',
    )
    async def htmx_admin_prize_category_create_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(request, tournament_id, prize_group_id)
        return self._render_prize_category_modal(web_context, action=FormAction.CREATE)

    @get(
        path=(
            '/prizes/prize-category-modal/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-update-modal',
    )
    async def htmx_admin_prize_category_update_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )

        prize_category = web_context.get_admin_prize_category()
        share_prizes = prize_category.are_prizes_shared
        data = WebContext.values_dict_to_form_data(
            {
                'name': prize_category.name,
                'is_main': prize_category.is_main,
                'sharing_threshold': prize_category.sharing_threshold,
                'share_prizes': share_prizes,
            }
        )
        if share_prizes:
            data['prize_sharing'] = prize_category.prize_sharing.id
        return self._render_prize_category_modal(
            web_context,
            action=FormAction.UPDATE,
            data=data,
        )

    @get(
        path=(
            '/prizes/prize-category-modal/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-delete-modal',
    )
    async def htmx_admin_prize_category_delete_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request, tournament_id, prize_group_id, prize_category_id
            ),
            {
                'modal': 'prize_category',
                'action': FormAction.DELETE,
            },
        )

    # -------------------------------------------------------------------------
    # Prize criteria
    # -------------------------------------------------------------------------

    @classmethod
    def _validate_prize_criterion_form_data(
        cls, event: Event, data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        field = 'type'
        player_filter_id = data.get(field, '')
        try:
            PrizePlayerFilterManager(event).get_type(player_filter_id)
        except KeyError:
            errors[field] = _('Please select a type of criterion.')
            return errors
        player_filter = cls.player_filter_from_data(event, data)
        try:
            player_filter.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
        return errors

    @staticmethod
    def player_filter_from_data(event: Event, data: dict[str, str]) -> PlayerFilter:
        player_filter_type = PrizePlayerFilterManager(event).get_type(data['type'])
        options = []
        for option in player_filter_type().default_options():
            value = WebContext.form_data_to_value(data, option.id, option.type)
            options.append(type(option)(value))
        return player_filter_type(options)

    @staticmethod
    def _prize_criterion_form_modal_context(
        web_context: PrizeAdminWebContext,
        data: dict[str, str],
        action: FormAction,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = web_context.request
        event = web_context.get_admin_event()
        player_filter_options = PlayerFilterOptionManager(event).objects()
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in player_filter_options
        } | {'type': ''}
        player_filter_select_options = {'': '-'} | PrizePlayerFilterManager(
            event
        ).options()
        for criterion in web_context.get_admin_prize_category().criteria:
            if (
                action == FormAction.UPDATE
                and criterion.id == web_context.get_admin_prize_criterion().id
            ):
                continue
            filter_id = criterion.player_filter.id
            if filter_id in player_filter_select_options:
                del player_filter_select_options[filter_id]
        return {
            'modal': 'prize_criterion_form',
            'action': action,
            'player_filter_select_options': player_filter_select_options,
            'player_filter_options': player_filter_options,
            'containers_by_type': {
                player_filter.id: [
                    option.container_id for option in player_filter.default_options()
                ]
                for player_filter in PrizePlayerFilterManager(event).objects()
            }
            | {'': []},
            'add_other_active': SessionPrizeCriteriaAddOtherActive(request).get(),
            'data': default_data | data,
            'errors': errors or {},
        }

    @post(
        path=(
            '/prizes/prize-criterion/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criterion-create',
        guards=manage_guards,
    )
    async def htmx_admin_prize_criterion_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )
        event = web_context.get_admin_event()

        flat_data = WebContext.flatten_list_data(data)
        add_other = WebContext.resolve_add_other(
            flat_data, SessionPrizeCriteriaAddOtherActive(request)
        )
        if errors := self._validate_prize_criterion_form_data(event, flat_data):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_criterion_form_modal_context(
                    web_context, flat_data, FormAction.CREATE, errors
                ),
            )
        prize_category = web_context.get_admin_prize_category()
        player_filter = self.player_filter_from_data(event, flat_data)
        criterion = prize_category.add_criterion(
            StoredPrizeCriterion(
                id=None,
                prize_category_id=prize_category.id,
                type=player_filter.id,
                options={option.id: option.value for option in player_filter.options},
            )
        )
        if add_other:
            template_context = self._prize_criterion_form_modal_context(
                web_context, {}, FormAction.CREATE, errors
            ) | {'previous_criterion': criterion}
        else:
            template_context = {'modal': 'prize_criteria'}
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/prizes/prize-criterion/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-update',
        guards=manage_guards,
    )
    async def htmx_admin_prize_criterion_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )
        event = web_context.get_admin_event()

        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_prize_criterion_form_data(event, flat_data):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_criterion_form_modal_context(
                    web_context, flat_data, FormAction.UPDATE, errors
                ),
            )
        player_filter = self.player_filter_from_data(event, flat_data)
        prize_criterion = web_context.get_admin_prize_criterion()
        stored_prize_criterion = prize_criterion.stored_prize_criterion
        stored_prize_criterion.type = player_filter.id
        stored_prize_criterion.options = {
            option.id: option.value for option in player_filter.options
        }
        prize_criterion.update()
        return self._admin_event_prizes_render(web_context, {'modal': 'prize_criteria'})

    @delete(
        path=(
            '/prizes/prize-criterion/delete/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-delete',
        guards=manage_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_criterion_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )

        prize_category = web_context.get_admin_prize_category()
        prize_category.delete_criterion(prize_criterion_id)
        return self._admin_event_prizes_render(web_context, {'modal': 'prize_criteria'})

    @get(
        path=(
            '/prizes/prize-criteria-modal/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criteria-modal',
    )
    async def htmx_admin_prize_criteria_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request, tournament_id, prize_group_id, prize_category_id
            ),
            {'modal': 'prize_criteria'},
        )

    @get(
        path=(
            '/prizes/criterion-modal/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criterion-create-modal',
    )
    async def htmx_admin_prize_criterion_create_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )
        return self._admin_event_prizes_render(
            web_context,
            self._prize_criterion_form_modal_context(
                web_context, {}, FormAction.CREATE
            ),
        )

    @get(
        path=(
            '/prizes/criterion-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-update-modal',
    )
    async def htmx_admin_prize_criterion_update_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )
        prize_criterion = web_context.get_admin_prize_criterion()
        data = {'type': prize_criterion.player_filter.id} | {
            option.id: WebContext.value_to_form_data(option.value)
            for option in prize_criterion.player_filter.options
        }
        return self._admin_event_prizes_render(
            web_context,
            self._prize_criterion_form_modal_context(
                web_context, data, FormAction.UPDATE
            ),
        )

    # -------------------------------------------------------------------------
    # Prizes
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_prize_form_data(
        data: dict[str, str], prize_category: PrizeCategory, action: FormAction
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        prize_type = PrizeTypeManager().get_object(
            WebContext.form_data_to_str(data, 'type') or ''
        )
        threshold = prize_category.sharing_threshold
        if action == FormAction.CREATE:
            field = 'values'
            str_values = WebContext.form_data_to_str(data, field) or ''
            for value in str_values.split(' '):
                if not value:
                    continue
                try:
                    float_value = float(value.replace(',', '.'))
                except ValueError:
                    errors[field] = _('[{value}] is not a valid value format.').format(
                        value=value
                    )
                    break
                if float_value < 0:
                    errors[field] = _('[{value}] is not a positive value.').format(
                        value=value
                    )
                    break
                if threshold and float_value < threshold:
                    errors[field] = _(
                        'The values have to be higher than the sharing '
                        'threshold of the category ({threshold}).'
                    ).format(
                        threshold=int(threshold)
                        if threshold.is_integer()
                        else threshold
                    )
                    break
            if not str_values and prize_type.is_monetary:
                errors[field] = _('At least one value is expected.')
        else:
            field = 'value'
            try:
                WebContext.form_data_to_float(data, field, 0, threshold or 0)
            except ValueError:
                errors[field] = (
                    _(
                        'The value has to be higher than the sharing '
                        'threshold of the category ({threshold}).'
                    ).format(
                        threshold=int(threshold)
                        if threshold.is_integer()
                        else threshold
                    )
                    if threshold
                    else _('A positive value is expected.')
                )
        if prize_type.has_description:
            description = (
                WebContext.form_data_to_str(data, field := 'description') or ''
            )
            if not description:
                errors[field] = _('This field is required.')
        return errors

    @staticmethod
    def _prize_form_modal_context(
        request: HTMXRequest,
        category: PrizeCategory,
        data: dict[str, str] | None = None,
        action: FormAction = FormAction.CREATE,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = {
            'values': '',
            'type': MonetaryPrizeType().id,
            'value': WebContext.value_to_form_data(0.0),
            'description': '',
        }
        prize_types = PrizeTypeManager().objects()
        type_options: dict[str, SelectOption] = {}
        for type_ in prize_types:
            option = SelectOption(type_.name, type_.tooltip_message)
            if not type_.is_monetary and category.are_prizes_shared:
                option.disabled = True
                option.tooltip = _(
                    'Non-monetary prizes are not compatible with '
                    'categories in which the prizes are shared.'
                )
            type_options[type_.id] = option
        return {
            'modal': 'prize_form',
            'prize_types': prize_types,
            'type_options': type_options,
            'add_other_active': SessionPrizesAddOtherActive(request).get(),
            'action': action,
            'data': default_data | (data or {}),
            'errors': errors or {},
        }

    @post(
        path=(
            '/prizes/prize/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-create',
        guards=manage_guards,
    )
    async def htmx_admin_prize_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )

        add_other = WebContext.resolve_add_other(
            data, SessionPrizesAddOtherActive(request)
        )
        prize_category = web_context.get_admin_prize_category()

        if errors := self._validate_prize_form_data(
            data, prize_category, FormAction.CREATE
        ):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_form_modal_context(
                    request, prize_category, data, errors=errors
                ),
            )
        type_id = WebContext.form_data_to_str(data, 'type') or ''
        description = WebContext.form_data_to_str(data, 'description') or ''
        str_values = WebContext.form_data_to_str(data, 'values') or '0'
        values = [
            float(value.replace(',', '.')) for value in str_values.split(' ') if value
        ]
        for value in values:
            prize_category.add_prize(
                StoredPrize(
                    id=None,
                    prize_category_id=prize_category.id,
                    type=type_id,
                    value=value,
                    description=description,
                )
            )
        if add_other:
            template_context = self._prize_form_modal_context(
                request, prize_category, errors=errors
            ) | {'previous_prize_count': len(values)}
        else:
            template_context = {'modal': 'prizes'}
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/prizes/prize/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-update',
        guards=manage_guards,
    )
    async def htmx_admin_prize_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )

        prize_category = web_context.get_admin_prize_category()
        if errors := self._validate_prize_form_data(
            data, prize_category, FormAction.UPDATE
        ):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_form_modal_context(
                    request, prize_category, data, FormAction.UPDATE, errors
                ),
            )
        prize = web_context.get_admin_prize()
        stored_prize = prize.stored_prize
        stored_prize.type = WebContext.form_data_to_str(data, 'type') or ''
        stored_prize.value = WebContext.form_data_to_float(data, 'value') or 0.0
        stored_prize.description = (
            WebContext.form_data_to_str(data, 'description') or ''
        )
        prize.update()
        return self._admin_event_prizes_render(web_context, {'modal': 'prizes'})

    @delete(
        path=(
            '/prizes/prize/delete/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-delete',
        guards=manage_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )

        prize_category = web_context.get_admin_prize_category()
        prize_category.delete_prize(prize_id)
        return self._admin_event_prizes_render(web_context, {'modal': 'prizes'})

    @get(
        path=(
            '/prizes/prizes-modal/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prizes-modal',
    )
    async def htmx_admin_prizes_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request,
                tournament_id,
                prize_group_id,
                prize_category_id,
            ),
            {'modal': 'prizes'},
        )

    @get(
        path=(
            '/prizes/prize-modal/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-create-modal',
    )
    async def htmx_admin_prize_create_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request, tournament_id, prize_group_id, prize_category_id
        )
        category = web_context.get_admin_prize_category()
        return self._admin_event_prizes_render(
            web_context, self._prize_form_modal_context(request, category)
        )

    @get(
        path=(
            '/prizes/prize-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-update-modal',
    )
    async def htmx_admin_prize_update_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template:
        web_context = PrizeAdminWebContext(
            request,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )
        category = web_context.get_admin_prize_category()
        prize = web_context.get_admin_prize()
        data = WebContext.values_dict_to_form_data(
            {
                'type': prize.type.id,
                'value': prize.value,
                'description': prize.description,
            }
        )
        return self._admin_event_prizes_render(
            web_context,
            self._prize_form_modal_context(request, category, data, FormAction.UPDATE),
        )
