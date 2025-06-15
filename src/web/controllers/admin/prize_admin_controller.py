import copy
from typing import Any, Annotated, TypedDict

from litestar import get, post, patch, delete
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXRequest, ClientRedirect

from common.i18n import _
from common.logger import get_logger
from data.prize.managers import (
    PrizeSharingManager,
    PlayerFilterManager,
    PlayerFilterOptionManager,
)
from data.prize.player_filters import PlayerFilter
from data.prize.prize import Prize
from data.prize.prize_category import PrizeCategory
from data.prize.prize_criterion import PrizeCriterion
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import NoPrizeSharing, AveragePrizeSharing
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPrizeGroup,
    StoredPrizeCategory,
    StoredPrize,
    StoredPrizeCriterion,
)
from utils import StaticUtils
from utils.enum import FormAction
from utils.option import OptionError
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


logger = get_logger()


class PrizeAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None = None,
        prize_group_id: int | None = None,
        prize_category_id: int | None = None,
        prize_criterion_id: int | None = None,
        prize_id: int | None = None,
        data: dict[str, str] | None = None,
    ):
        super().__init__(request, event_uniq_id, data)
        self.admin_tournament: Tournament | None = None
        self.admin_prize_group: PrizeGroup | None = None
        self.admin_prize_category: PrizeCategory | None = None
        self.admin_prize_criterion: PrizeCriterion | None = None
        self.admin_prize: Prize | None = None
        if not self.admin_event:
            return

        event = self.get_admin_event()
        if tournament_id:
            if tournament_id not in event.tournaments_by_id:
                self._redirect_error(
                    f'Unknown tournament ID [{tournament_id}] '
                    f'for event [{event_uniq_id}]'
                )
                return
            self.admin_tournament = event.tournaments_by_id[tournament_id]
        elif event.tournaments:
            self.admin_tournament = event.tournaments_sorted_by_uniq_id[0]

        if prize_group_id:
            tournament = self.get_admin_tournament()
            if prize_group_id not in tournament.prize_groups_by_id:
                self._redirect_error(
                    f'Unknown prize group ID [{prize_group_id}] for '
                    f'tournament [{tournament_id}] of event [{event_uniq_id}]'
                )
                return
            self.admin_prize_group = tournament.prize_groups_by_id[prize_group_id]
        else:
            self.set_default_prize_group()

        if prize_category_id:
            prize_group = self.get_admin_prize_group()
            if prize_category_id not in prize_group.categories_by_id:
                self._redirect_error(
                    f'Unknown category ID [{prize_category_id}] for '
                    f'prize group [{prize_group_id}]'
                )
                return
            self.admin_prize_category = prize_group.categories_by_id[prize_category_id]

        if prize_criterion_id:
            prize_category = self.get_admin_prize_category()
            if prize_criterion_id not in prize_category.criteria_by_id:
                self._redirect_error(
                    f'Unknown criterion ID [{prize_criterion_id}] for '
                    f'prize category [{prize_category_id}]'
                )
                return
            self.admin_prize_criterion = prize_category.criteria_by_id[
                prize_criterion_id
            ]

        if prize_id:
            prize_category = self.get_admin_prize_category()
            if prize_id not in prize_category.prizes_by_id:
                self._redirect_error(
                    f'Unknown prize ID [{prize_id}] for '
                    f'prize category [{prize_category_id}]'
                )
                return
            self.admin_prize = prize_category.prizes_by_id[prize_id]

    def set_default_prize_group(self):
        if self.admin_tournament and self.admin_tournament.prize_groups:
            self.admin_prize_group = self.admin_tournament.sorted_prize_groups[0]
        else:
            self.admin_prize_group = None

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': 'admin-event-prizes-tab',
            'admin_tournament': self.admin_tournament,
            'admin_prize_group': self.admin_prize_group,
            'admin_prize_category': self.admin_prize_category,
            'admin_prize_criterion': self.admin_prize_criterion,
            'admin_prize': self.admin_prize,
            'ordinal_integer': StaticUtils.ordinal_integer,
            'tournament_options': self.get_tournament_options(),
            'prize_group_options': self.get_prize_group_options(),
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
    @classmethod
    def _admin_event_prizes_render(
        cls,
        web_context: PrizeAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template | ClientRedirect:
        if web_context.error:
            return web_context.error
        return cls._admin_event_render(
            cls._get_admin_event_render_context(web_context) | (template_context or {})
        )

    @get(
        path=[
            '/admin/event/{event_uniq_id:str}/prizes',
            '/admin/event/{event_uniq_id:str}/prizes/{tournament_id:int}',
            '/admin/event/{event_uniq_id:str}/prizes/{tournament_id:int}/{prize_group_id:int}',
        ],
        name='admin-event-prizes-tab',
        cache=1,
    )
    async def htmx_admin_prizes_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        prize_group_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(request, event_uniq_id, tournament_id, prize_group_id)
        )

    # -------------------------------------------------------------------------
    # Prize groups
    # -------------------------------------------------------------------------

    @post(
        path='/admin/prizes/prize-group/create/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-prize-group-create',
    )
    async def htmx_admin_prize_group_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(request, event_uniq_id, tournament_id)
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        prize_group = tournament.add_prize_group(
            StoredPrizeGroup(
                id=None,
                tournament_id=tournament.id,
                name=WebContext.form_data_to_str(data, 'name') or '',
            )
        )
        web_context.admin_prize_group = prize_group
        Message.success(
            request,
            _('Prize group [{prize_group}] successfully created.').format(
                prize_group=prize_group.name
            ),
        )
        return self._admin_event_prizes_render(web_context)

    @patch(
        path=(
            '/admin/prizes/prize-group/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-update',
    )
    async def htmx_admin_prize_group_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id
        )
        if web_context.error:
            return web_context.error
        prize_group = web_context.get_admin_prize_group()
        previous_name = prize_group.name
        prize_group.stored_prize_group.name = (
            WebContext.form_data_to_str(data, 'name') or ''
        )
        prize_group.update()
        Message.success(
            request,
            _(
                'Prize group [{prize_group_old}] successfully'
                ' renamed to [{prize_group_new}].'
            ).format(
                prize_group_old=previous_name,
                prize_group_new=prize_group.name,
            ),
        )
        return self._admin_event_prizes_render(web_context)

    @delete(
        path=(
            '/admin/prizes/prize-group/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_group_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        prize_group = web_context.get_admin_prize_group()
        tournament.delete_prize_group(prize_group_id)
        Message.success(
            request,
            _('Prize group [{prize_group}] successfully deleted.').format(
                prize_group=prize_group.name
            ),
        )
        web_context.set_default_prize_group()
        return self._admin_event_prizes_render(web_context)

    @get(
        path=(
            '/admin/prizes/prize-group-modal/delete/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-group-delete-modal',
    )
    async def htmx_admin_prize_group_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(request, event_uniq_id, tournament_id, prize_group_id),
            {
                'modal': 'prize_group',
                'action': FormAction.DELETE,
            },
        )

    # -------------------------------------------------------------------------
    # Prize categories
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_prize_category_form_data(
        data: dict[str, str], prize_category: PrizeCategory | None = None
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        field = 'name'
        if not WebContext.form_data_to_str(data, field):
            errors[field] = _('Please enter a name.')
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
                PrizeSharingManager.get_object(prize_sharing_id)
            except KeyError:
                message = f'Unknown prize sharing ID [{prize_sharing_id}]'
                errors[field] = message
                logger.error(message)
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
        return errors

    @staticmethod
    def _prize_category_modal_context(
        data: dict[str, str], action: FormAction, errors: dict[str, str] | None = None
    ) -> dict[str, Any]:
        prize_sharing_options = PrizeSharingManager.options()
        prize_sharing_options.pop(NoPrizeSharing.static_id())
        return {
            'modal': 'prize_category',
            'action': action,
            'prize_sharing_options': prize_sharing_options,
            'data': data,
            'errors': errors or {},
        }

    @staticmethod
    def _prize_category_default_form_data(tournament: Tournament) -> dict[str, str]:
        return {
            'name': '',
            'is_main': WebContext.value_to_form_data(
                not tournament.has_main_prize_category
            ),
            'share_prizes': WebContext.value_to_form_data(False),
            'sharing_threshold': '',
            'prize_sharing': AveragePrizeSharing.static_id(),
        }

    @post(
        path=(
            '/admin/prizes/prize-category/create/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-category-create',
    )
    async def htmx_admin_prize_category_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id
        )
        if web_context.error:
            return web_context.error
        if errors := self._validate_prize_category_form_data(data):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_category_modal_context(data, FormAction.CREATE, errors),
            )
        prize_group = web_context.get_admin_prize_group()
        share_prizes = WebContext.form_data_to_bool(data, 'share_prizes')
        prize_category = prize_group.add_category(
            StoredPrizeCategory(
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
                    data['prize_sharing']
                    if share_prizes
                    else NoPrizeSharing.static_id()
                ),
                index=len(prize_group.categories),
            )
        )
        if 'add_other' in data:
            data = self._prize_category_default_form_data(prize_group.tournament)
            template_context = self._prize_category_modal_context(
                data, FormAction.CREATE, errors
            ) | {'previous_category': prize_category}
        else:
            template_context = {}
            Message.success(
                request,
                _('Prize category [{prize_category}] successfully created.').format(
                    prize_category=prize_category.name
                ),
            )
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/admin/prizes/prize-category/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-update',
    )
    async def htmx_admin_prize_category_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        if errors := self._validate_prize_category_form_data(data, prize_category):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_category_modal_context(data, FormAction.UPDATE, errors),
            )
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
        Message.success(
            request,
            _('Prize category [{prize_category}] successfully updated.').format(
                prize_category=prize_category.name
            ),
        )
        return self._admin_event_prizes_render(web_context)

    @delete(
        path=(
            '/admin/prizes/prize-category/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_category_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
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
            '/admin/prizes/prize-category/duplicate/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-duplicate',
    )
    async def htmx_admin_prize_category_duplicate(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
        prize_group = web_context.get_admin_prize_group()
        copy_category = web_context.get_admin_prize_category()
        stored_category = copy.deepcopy(copy_category.stored_prize_category)
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

    class ReorderFormData(TypedDict):
        item: list[int]

    @patch(
        path='/admin/prizes/prize-category/reorder/{event_uniq_id:str}',
        name='admin-prizes-reorder-categories',
    )
    async def htmx_admin_screen_reorder_sets(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            ReorderFormData,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        prize_group = web_context.get_admin_prize_group()
        prize_group.reorder_categories(data['item'])
        return self._admin_event_prizes_render(web_context)

    @get(
        path=(
            '/admin/prizes/prize-category-modal/create/'
            '{event_uniq_id:str}/{tournament_id:int}/{prize_group_id:int}'
        ),
        name='admin-prize-category-create-modal',
    )
    async def htmx_admin_prize_category_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id
        )
        if web_context.error:
            return web_context.error
        data = self._prize_category_default_form_data(
            web_context.get_admin_tournament()
        )
        return self._admin_event_prizes_render(
            web_context,
            self._prize_category_modal_context(data, FormAction.CREATE),
        )

    @get(
        path=(
            '/admin/prizes/prize-category-modal/update/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-update-modal',
    )
    async def htmx_admin_prize_category_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        share_prizes = prize_category.are_prizes_shared
        data = {
            'name': WebContext.value_to_form_data(prize_category.name),
            'is_main': WebContext.value_to_form_data(prize_category.is_main),
            'sharing_threshold': WebContext.value_to_form_data(
                prize_category.sharing_threshold
            ),
            'share_prizes': WebContext.value_to_form_data(share_prizes),
        }
        if share_prizes:
            data['prize_sharing'] = prize_category.prize_sharing.id
        return self._admin_event_prizes_render(
            web_context,
            self._prize_category_modal_context(data, FormAction.UPDATE),
        )

    @get(
        path=(
            '/admin/prizes/prize-category-modal/delete/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-category-delete-modal',
    )
    async def htmx_admin_prize_category_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
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
        cls, data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        field = 'type'
        player_filter_id = data.get(field, '')
        try:
            PlayerFilterManager.get_type(player_filter_id)
        except KeyError:
            errors[field] = _('Please select a type of criterion.')
            return errors
        player_filter = cls.player_filter_from_data(data)
        try:
            player_filter.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
        return errors

    @staticmethod
    def player_filter_from_data(data: dict[str, str]) -> PlayerFilter:
        player_filter_type = PlayerFilterManager.get_type(data['type'])
        options = []
        for option in player_filter_type.default_options():
            value = WebContext.form_data_to_value(data, option.id, option.type)
            options.append(type(option)(value))
        return player_filter_type(options)

    @staticmethod
    def _prize_criterion_form_modal_context(
        data: dict[str, str], action: FormAction, errors: dict[str, str] | None = None
    ) -> dict[str, Any]:
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in PlayerFilterOptionManager.objects()
        } | {'type': ''}
        return {
            'modal': 'prize_criterion_form',
            'action': action,
            'player_filter_select_options': {'': '-'} | PlayerFilterManager.options(),
            'player_filter_options': PlayerFilterOptionManager.objects(),
            'containers_by_type': {
                player_filter.id: [
                    option.container_id for option in player_filter.default_options()
                ]
                for player_filter in PlayerFilterManager.objects()
            }
            | {'': []},
            'data': default_data | data,
            'errors': errors or {},
        }

    @post(
        path=(
            '/admin/prizes/prize-criterion/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criterion-create',
    )
    async def htmx_admin_prize_criterion_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_prize_criterion_form_data(flat_data):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_criterion_form_modal_context(
                    flat_data, FormAction.CREATE, errors
                ),
            )
        prize_category = web_context.get_admin_prize_category()
        player_filter = self.player_filter_from_data(flat_data)
        criterion = prize_category.add_criterion(
            StoredPrizeCriterion(
                id=None,
                prize_category_id=prize_category.id,
                type=player_filter.id,
                options={option.id: option.value for option in player_filter.options},
            )
        )
        if 'add_other' in data:
            template_context = self._prize_criterion_form_modal_context(
                {}, FormAction.CREATE, errors
            ) | {'previous_criterion': criterion}
        else:
            template_context = {'modal': 'prize_criteria'}
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/admin/prizes/prize-criterion/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-update',
    )
    async def htmx_admin_prize_criterion_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_prize_criterion_form_data(flat_data):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_criterion_form_modal_context(
                    flat_data, FormAction.UPDATE, errors
                ),
            )
        player_filter = self.player_filter_from_data(flat_data)
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
            '/admin/prizes/prize-criterion/delete/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_criterion_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        prize_category.delete_criterion(prize_criterion_id)
        return self._admin_event_prizes_render(web_context, {'modal': 'prize_criteria'})

    @get(
        path=(
            '/admin/prizes/prize-criteria-modal/{event_uniq_id:str}/'
            '{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criteria-modal',
    )
    async def htmx_admin_prize_criteria_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
            ),
            {'modal': 'prize_criteria'},
        )

    @get(
        path=(
            '/admin/prizes/criterion-modal/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-criterion-create-modal',
    )
    async def htmx_admin_prize_criterion_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        return self._admin_event_prizes_render(
            web_context,
            self._prize_criterion_form_modal_context({}, FormAction.CREATE),
        )

    @get(
        path=(
            '/admin/prizes/criterion-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_criterion_id:int}'
        ),
        name='admin-prize-criterion-update-modal',
    )
    async def htmx_admin_prize_criterion_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_criterion_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_criterion_id=prize_criterion_id,
        )
        if web_context.error:
            return web_context.error
        prize_criterion = web_context.get_admin_prize_criterion()
        data = {'type': prize_criterion.player_filter.id} | {
            option.id: WebContext.value_to_form_data(option.value)
            for option in prize_criterion.player_filter.options
        }
        return self._admin_event_prizes_render(
            web_context,
            self._prize_criterion_form_modal_context(data, FormAction.UPDATE),
        )

    # -------------------------------------------------------------------------
    # Prizes
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_prize_form_data(
        data: dict[str, str], prize_category: PrizeCategory
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        is_monetary = WebContext.form_data_to_bool(data, 'is_monetary')
        field = 'value'
        threshold = prize_category.sharing_threshold
        try:
            WebContext.form_data_to_float(data, field, 0, threshold or 0)
        except ValueError:
            errors[field] = (
                _(
                    'The value has to be higher than the sharing '
                    'threshold of the category ({threshold}).'
                ).format(
                    threshold=int(threshold) if threshold.is_integer() else threshold
                )
                if threshold
                else _('A positive value is expected.')
            )
        field = 'description'
        description = WebContext.form_data_to_str(data, field) or ''
        if is_monetary and description:
            message = 'Description is only allowed for non-monetary prizes.'
            errors[field] = message
            logger.error(message)
        if not is_monetary and not description:
            errors[field] = _('Description is mandatory for non-monetary prizes.')
        return errors

    @staticmethod
    def _prize_form_modal_context(
        data: dict[str, str], action: FormAction, errors: dict[str, str] | None = None
    ) -> dict[str, Any]:
        default_data = {
            'value': WebContext.value_to_form_data(0.0),
            'is_monetary': WebContext.value_to_form_data(True),
            'description': '',
        }
        return {
            'modal': 'prize_form',
            'action': action,
            'data': default_data | (data or {}),
            'errors': errors or {},
        }

    @post(
        path=(
            '/admin/prizes/prize/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-create',
    )
    async def htmx_admin_prize_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        if errors := self._validate_prize_form_data(data, prize_category):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_form_modal_context(data, FormAction.CREATE, errors),
            )
        value = web_context.form_data_to_float(data, 'value') or 0.0
        prize = prize_category.add_prize(
            StoredPrize(
                id=None,
                prize_category_id=prize_category.id,
                value=value,
                is_monetary=WebContext.form_data_to_bool(data, 'is_monetary'),
                description=WebContext.form_data_to_str(data, 'description') or '',
            )
        )
        if 'add_other' in data:
            template_context = self._prize_form_modal_context(
                {}, FormAction.CREATE, errors
            ) | {'previous_prize': prize}
        else:
            template_context = {'modal': 'prizes'}
        return self._admin_event_prizes_render(web_context, template_context)

    @patch(
        path=(
            '/admin/prizes/prize/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-update',
    )
    async def htmx_admin_prize_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        if errors := self._validate_prize_form_data(data, prize_category):
            return self._admin_event_prizes_render(
                web_context,
                self._prize_form_modal_context(data, FormAction.UPDATE, errors),
            )
        prize = web_context.get_admin_prize()
        stored_prize = prize.stored_prize

        stored_prize.value = WebContext.form_data_to_float(data, 'value') or 0.0
        stored_prize.is_monetary = WebContext.form_data_to_bool(data, 'is_monetary')
        stored_prize.description = (
            WebContext.form_data_to_str(data, 'description') or ''
        )
        prize.update()
        return self._admin_event_prizes_render(web_context, {'modal': 'prizes'})

    @delete(
        path=(
            '/admin/prizes/prize/delete/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_prize_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )
        if web_context.error:
            return web_context.error
        prize_category = web_context.get_admin_prize_category()
        prize_category.delete_prize(prize_id)
        return self._admin_event_prizes_render(web_context, {'modal': 'prizes'})

    @get(
        path=(
            '/admin/prizes/prizes-modal/{event_uniq_id:str}/{tournament_id:int}'
            '/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prizes-modal',
    )
    async def htmx_admin_prizes_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_prizes_render(
            PrizeAdminWebContext(
                request,
                event_uniq_id,
                tournament_id,
                prize_group_id,
                prize_category_id,
            ),
            {'modal': 'prizes'},
        )

    @get(
        path=(
            '/admin/prizes/prize-modal/create/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}/{prize_category_id:int}'
        ),
        name='admin-prize-create-modal',
    )
    async def htmx_admin_prize_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request, event_uniq_id, tournament_id, prize_group_id, prize_category_id
        )
        return self._admin_event_prizes_render(
            web_context,
            self._prize_form_modal_context({}, FormAction.CREATE),
        )

    @get(
        path=(
            '/admin/prizes/prize-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{prize_group_id:int}'
            '/{prize_category_id:int}/{prize_id:int}'
        ),
        name='admin-prize-update-modal',
    )
    async def htmx_admin_prize_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        prize_group_id: int,
        prize_category_id: int,
        prize_id: int,
    ) -> Template | ClientRedirect:
        web_context = PrizeAdminWebContext(
            request,
            event_uniq_id,
            tournament_id,
            prize_group_id,
            prize_category_id,
            prize_id=prize_id,
        )
        if web_context.error:
            return web_context.error
        prize = web_context.get_admin_prize()
        data = {
            'value': WebContext.value_to_form_data(prize.value),
            'is_monetary': WebContext.value_to_form_data(prize.is_monetary),
            'description': WebContext.value_to_form_data(prize.description),
        }
        return self._admin_event_prizes_render(
            web_context,
            self._prize_form_modal_context(data, FormAction.UPDATE),
        )
