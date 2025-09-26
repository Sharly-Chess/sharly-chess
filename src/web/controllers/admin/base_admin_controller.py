from pathlib import Path
from typing import Any

import requests
import validators
from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest

from common import REQUEST_TIMEOUT
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from utils.enum import TournamentRating
from plugins.manager import plugin_manager
from web.controllers.base_controller import BaseController, WebContext
from web.utils import RequestUtils


class AdminWebContext(WebContext):
    """
    The basic admin web context.
    """

    def __init__(
        self,
        request: HTMXRequest,
        admin_tab: str | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request)
        self.admin_tab: str | None = admin_tab
        self.admin_event: Event | None = None
        self.admin_event = RequestUtils.get_optional_event(request, reload_event)
        self.check_admin_tab()

    def get_admin_event(self) -> Event:
        assert self.admin_event is not None
        return self.admin_event

    def check_admin_tab(self):
        if self.admin_tab not in [
            None,
            'home',
            'passed_events',
            'current_events',
            'coming_events',
            'archives',
        ]:
            raise NotFoundException(
                f'Invalid value [{self.admin_tab}] for parameter [admin_tab]'
            )

    @property
    def background_image(self) -> str | None:
        return None

    @property
    def background_color(self) -> str:
        return SharlyChessConfig.admin_background_color

    @property
    def theme(self) -> str:
        return 'dark'

    @property
    def template_context(self) -> dict[str, Any]:
        per_plugin_context = plugin_manager.hook.get_base_admin_template_context()
        plugin_context = {
            key: value
            for context in per_plugin_context
            for key, value in context.items()
        }

        return (
            super().template_context
            | {
                'admin_tab': self.admin_tab,
                'admin_event': self.admin_event,
            }
            | plugin_context
        )


class BaseAdminController(BaseController):
    """A base class inherited by all the admin controllers."""

    @staticmethod
    def _get_federation_options() -> dict[str, str]:
        return {
            federation_id: f'{federation_id} - {federation_name}'
            for federation_id, federation_name in SharlyChessConfig.federations.items()
        }

    @staticmethod
    def _get_rating_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(rating.value): rating.short_name
            for rating in TournamentRating
        }

    @staticmethod
    def _get_timer_color_texts(delays: dict[int, int]) -> dict[int, str]:
        return {
            1: _(
                'Colour #1 is used until {delay_1} minutes before the start of the rounds (delay #1), the color then changes gradually until colour #2 ({delay_2} minutes before the start of the rounds).'
            ).format(delay_1=delays[1], delay_2=delays[2]),
            2: _(
                'Colour #2 is used {delay_2} minutes before the start of the rounds (delay #2), the color then changes gradually until colour #3 (at the start of the rounds).'
            ).format(delay_2=delays[2]),
            3: _(
                'Colour #3 is used from the start of the rounds and for {delay_3} minutes after (delay #3).'
            ).format(delay_3=delays[3]),
        }

    @staticmethod
    def _get_screen_type_options(family_screens_only: bool) -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'input': _('Check-in / Results entry'),
            'boards': _('Pairings by board'),
            'players': _('Pairings by player'),
        }
        if not family_screens_only:
            options['results'] = _('Last results')
            options['image'] = _('Image')
        return options

    @staticmethod
    def _get_timer_options(event: Event) -> dict[str, str]:
        return {'': '-'} | {
            str(timer.id): timer.name for timer in event.timers_by_id.values()
        }

    @staticmethod
    def _get_input_exit_button_options() -> dict[str, str]:
        options: dict[str, str] = {
            'on': _('Display the exit button'),
            'off': _('Hide the exit button'),
        }
        return options

    @staticmethod
    def _get_players_show_unpaired_options() -> dict[str, str]:
        options: dict[str, str] = {
            'off': _('Display only paired players'),
            'on': _('Display all the players, paired and unpaired'),
        }
        return options

    @staticmethod
    def _get_players_show_opponent_options() -> dict[str, str]:
        options: dict[str, str] = {
            'off': _('Display only color and board number'),
            'on': _('Display color, board number and opponent'),
        }
        return options

    @staticmethod
    def _get_ranking_crosstable_options() -> dict[str, str]:
        options: dict[str, str] = {
            'on': _('Crosstable'),
            'off': _('Ranking only'),
        }
        return options

    @staticmethod
    def _admin_validate_record_illegal_moves_update_data(
        data: dict[str, str],
        errors: dict[str, str],
    ) -> int | None:
        field = 'record_illegal_moves'
        record_illegal_moves: int | None
        try:
            record_illegal_moves = WebContext.form_data_to_int(data, field)
            assert record_illegal_moves is None or 0 <= record_illegal_moves <= 3
        except (ValueError, AssertionError):
            record_illegal_moves = None
            errors['record_illegal_moves'] = _('Invalid value [{value}].').format(
                value=data[field]
            )
        return record_illegal_moves

    @staticmethod
    def _admin_validate_rules_update_data(
        data: dict[str, str],
        errors: dict[str, str],
    ) -> str | None:
        field = 'rules'
        rules: str | None = WebContext.form_data_to_str(data, field)
        if rules:
            if validators.url(rules):
                try:
                    response = requests.get(rules, timeout=REQUEST_TIMEOUT)
                    if response.status_code != 200:
                        errors[field] = _(
                            'URL [{url}] responded code [{code}].'
                        ).format(url=rules, code=response.status_code)
                except requests.ConnectionError as ce:
                    errors[field] = _(
                        'URL [{url}] did not respond (error: [{error}]).'
                    ).format(url=rules, error=str(ce))
            else:
                # Remove quotes around the path if they exist
                # A user who used "Copy as Path" in the Windows File Explorer will have these quotes.
                rules = rules.strip('"\'')

                if rules.find('..') != -1:
                    errors[field] = _('Incorrect path [{path}].').format(path=rules)
                    data[field] = ''
                else:
                    file: Path = Path(rules)
                    if not file.exists() or not file.is_file():
                        errors[field] = _('File [{file}] not found.').format(file=rules)
                    elif file.suffix.lower() != '.pdf':
                        errors[field] = _(
                            'Wrong file extension [{ext}] ([pdf] expected).'
                        ).format(ext=file.suffix)
        return rules

    @staticmethod
    def _admin_validate_background_color_update_data(
        data: dict[str, str],
        errors: dict[str, str],
    ) -> str | None:
        field = 'background_color'
        background_color: str | None = None
        color_checkbox = WebContext.form_data_to_bool(data, field + '_checkbox')
        if not color_checkbox:
            try:
                background_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
        return background_color

    @staticmethod
    def background_images_jstree_data(background_image: str) -> list[dict[str, Any]]:
        dirs: list[str] = []
        files: list[str] = []
        for custom_path in [
            SharlyChessConfig.embedded_custom_path,
            SharlyChessConfig.custom_path,
        ]:
            for item in custom_path.rglob('*'):
                item_str = (
                    str(item)
                    .replace(str(custom_path), '')
                    .replace('\\', '/')
                    .lstrip('/')
                )
                if item.is_dir():
                    if item_str not in dirs:
                        dirs.append(item_str)
                else:
                    if item_str not in files:
                        files.append(item_str)
        dir_nodes: list[dict[str, Any]] = [
            {
                'id': d or '#',
                'parent': '/'.join(d.split('/')[:-1]) or '#',
                'text': f' {d.split("/")[-1]}',
                'state': {},
                'icon': 'bi-folder',
            }
            for d in dirs
        ]
        file_nodes: list[dict[str, Any]] = [
            {
                'id': f or '#',
                'parent': '/'.join(f.split('/')[:-1]) or '#',
                'text': f.split('/')[-1],
                'state': {
                    'selected': background_image == f,
                },
                'icon': 'bi-card-image',
                'a_attr': {
                    'onclick': f'$("#background-image").val("{f}"); '
                    f'$.ajax({{'
                    f'    url: "/background",'
                    f'    type: "GET",'
                    f'    data: {{ "image": "{f}", "color": $("#background-color").val() }},'
                    f'    success: function(data) {{'
                    f'        $("#background-image-test").css("background-image", data["url"]);'
                    f'    }},'
                    f'    error: function(jqXHR, exception) {{'
                    f'        console.log('
                    f'            "Changing background failed: status_code=" + jqXHR.status '
                    f'            + ", exception=" + exception + ", response=" + jqXHR.responseText'
                    f'        );'
                    f'    }},'
                    f'}});',
                },
            }
            for f in files
        ]
        return file_nodes + dir_nodes
