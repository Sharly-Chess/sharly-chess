import copy
import math
import urllib.parse
from pathlib import PurePosixPath
from collections import defaultdict
from datetime import date
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from litestar import delete, get, patch, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Body, FromPath, FromQuery
from litestar.plugins.htmx import ClientRedirect, HTMXRequest, HTMXTemplate
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.exception import FormError, OptionError
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.criteria.player_filters import (
    AgePlayerFilter,
    GenderPlayerFilter,
    PlayerFilter,
)
from data.championship.documents import (
    ChampionshipCompetitorListPrintDocument,
    ChampionshipPrintOption,
    ChampionshipRankingsPrintDocument,
    ChampionshipTournamentListPrintDocument,
    TournamentNamePrintOption,
    championship_print_document_type,
    championship_print_documents,
)
from data.championship.championship import Championship, ChampionshipSource
from data.championship.championship_loader import (
    ChampionshipArchiveLoader,
    ChampionshipLoader,
)
from data.championship.options import (
    ChampionshipCompetitorType,
    TeamScoreBasis,
)
from data.championship.scoring import (
    ChampionshipRule,
    DirectEncounterRule,
    ScoringContext,
    DEFAULT_F1_POINTS,
    F1PointsRule,
    ManualRule,
    TotalPointsRule,
    best_participations,
    build_rule,
    championship_rule_class,
    championship_rules,
    aggregatable_tie_break_types,
    rank_competitors,
)
from data.loader import EventLoader
from data.player_categories import (
    SELECTABLE_JUNIOR_CATEGORIES,
    SELECTABLE_SENIOR_CATEGORIES,
)
from database.sqlite.championship.championship_store import (
    StoredChampionshipCategory,
    StoredChampionshipCriterion,
    StoredChampionshipRule,
)
from utils.enum import PlayerGender
from utils.date_time import format_date
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.controllers.admin.index_admin_controller import IndexAdminController
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard
from web.messages import Message
from web.streaming_template import StreamingHTMXTemplate
from web.session import (
    SessionChampionshipCategoriesAddOtherActive,
    SessionChampionshipCriteriaAddOtherActive,
    SessionChampionshipSourcesAddOtherActive,
)
from web.utils import SelectOption


ChampionshipTab = Literal['sources', 'competitors', 'configuration', 'results']
CHAMPIONSHIP_PLAYER_FILTER_TYPES: tuple[type[PlayerFilter], ...] = (
    AgePlayerFilter,
    GenderPlayerFilter,
)


class ChampionshipAdminController(BaseAdminController):
    """Administration pages for cross-event Championship standings."""

    # Competitors are loaded a page at a time (infinite scroll) so a large
    # field does not render thousands of rows in one response.
    COMPETITOR_PAGE_SIZE = 50

    @staticmethod
    def _load_championship(uniq_id: str) -> Championship:
        loader = ChampionshipLoader()
        if uniq_id not in loader.all_championship_ids():
            raise NotFoundException(f'Championship [{uniq_id}] not found')
        return loader.load_championship(uniq_id)

    @staticmethod
    def _score(value: float | int) -> str:
        value = float(value)
        return str(int(value)) if value.is_integer() else f'{value:g}'

    @classmethod
    def _source_events(cls, championship: Championship) -> list[dict[str, Any]]:
        existing = {
            (source.event_uniq_id, source.tournament_id)
            for source in championship.sources
        }
        want_team = championship.competitor_type == ChampionshipCompetitorType.TEAM
        source_events: list[dict[str, Any]] = []
        event_loader = EventLoader()
        for event_uniq_id in event_loader.event_uniq_ids:
            try:
                event = event_loader.load_event(event_uniq_id)
            except Exception:
                continue
            if event.is_team_event != want_team:
                continue
            tournaments = [
                {
                    'id': tournament.id,
                    'name': tournament.name,
                    'start_date': tournament.start_date,
                }
                for tournament in event.tournaments
                if (event_uniq_id, tournament.id) not in existing
            ]
            if tournaments:
                source_events.append(
                    {
                        'uniq_id': event_uniq_id,
                        'name': event.name,
                        'tournaments': sorted(
                            tournaments,
                            key=lambda tournament: (
                                tournament['start_date'],
                                tournament['name'].casefold(),
                            ),
                        ),
                    }
                )
        return sorted(
            source_events,
            key=lambda event: event['name'].casefold(),
        )

    @staticmethod
    def _stage_rules(championship: Championship) -> list:
        """One rule per distinct per-stage metric, in chain order. These are the
        value columns of the per-stage breakdown popover: rules with no per-stage
        value (direct encounter, manual) are dropped, and rules sharing a metric
        (e.g. ``Pts4`` and ``Pts5``, or sum/average of the same tie-break) are
        collapsed to a single column since best-N does not change a stage value."""
        rules = []
        seen: set[str] = set()
        for rule in championship.rules:
            if type(rule).stage_display is ChampionshipRule.stage_display:
                continue
            if rule.stage_metric in seen:
                continue
            seen.add(rule.stage_metric)
            rules.append(rule)
        return rules

    @classmethod
    def _competitor_rows(cls, championship: Championship) -> list[dict[str, Any]]:
        rows = []
        for competitor in championship.competitors:
            # A player or a team; the fields read below depend on which, and the
            # branches pick the right ones, so treat it dynamically here.
            competitor = cast(Any, competitor)
            if championship.competitor_type == ChampionshipCompetitorType.TEAM:
                name = competitor.name
                secondary = competitor.federation
            else:
                name = f'{competitor.last_name}, {competitor.first_name}'
                secondary = str(competitor.fide_id or '')
            participations = []
            categories: list[str] = []
            genders: list[str] = []
            override_group_keys: list[str] = []
            # Tournaments in the order they were played (undated ones last).
            ordered_participations = sorted(
                competitor.participations,
                key=lambda participation: (
                    getattr(participation.source, 'start_date', None) is None,
                    getattr(participation.source, 'start_date', None) or date.max,
                ),
            )
            for participation in ordered_participations:
                source_competitor = getattr(
                    participation,
                    'tournament_player',
                    getattr(participation, 'team', None),
                )
                if (
                    championship.competitor_type
                    == ChampionshipCompetitorType.INDIVIDUAL
                ):
                    category = getattr(source_competitor, 'category', None)
                    category_name = getattr(category, 'name', '')
                    if category_name and category_name not in categories:
                        categories.append(category_name)
                    gender = getattr(source_competitor, 'gender', None)
                    gender_name = getattr(gender, 'short_name', '')
                    if gender_name and gender_name not in genders:
                        genders.append(gender_name)
                ref = (
                    participation.event_uniq_id,
                    participation.tournament_id,
                    participation.source_competitor_id,
                )
                overrides = (
                    championship.stored_championship.stored_team_overrides
                    if championship.competitor_type == ChampionshipCompetitorType.TEAM
                    else championship.stored_championship.stored_player_overrides
                )
                override = next(
                    (
                        item
                        for item in overrides
                        if (
                            item.event_uniq_id,
                            item.tournament_id,
                            getattr(
                                item,
                                'source_team_id',
                                getattr(item, 'source_player_id', None),
                            ),
                        )
                        == ref
                    ),
                    None,
                )
                if override and override.group_key not in override_group_keys:
                    override_group_keys.append(override.group_key)
                participations.append(
                    {
                        'ref': '|'.join(str(value) for value in ref),
                        'event_uniq_id': ref[0],
                        'tournament_id': ref[1],
                        'competitor_id': ref[2],
                        'source_name': participation.source.tournament_name,
                        'name': getattr(source_competitor, 'name', None)
                        or getattr(source_competitor, 'full_name', name),
                        'override': override,
                    }
                )
            rows.append(
                {
                    'name': name,
                    'secondary': secondary,
                    'category': ' / '.join(categories),
                    'gender': ' / '.join(genders),
                    'participations': participations,
                    'override_group_keys': override_group_keys,
                    'refs': ';'.join(
                        participation['ref'] for participation in participations
                    ),
                }
            )
        return sorted(rows, key=lambda row: row['name'].casefold())

    @classmethod
    def _competitor_page_context(
        cls, championship: Championship, page: int
    ) -> dict[str, Any]:
        """One page of the (sorted) competitor rows, plus the paging state the
        infinite-scroll template needs to fetch the next page."""
        rows = cls._competitor_rows(championship)
        page = max(1, page)
        pages = max(1, math.ceil(len(rows) / cls.COMPETITOR_PAGE_SIZE))
        start = (page - 1) * cls.COMPETITOR_PAGE_SIZE
        return {
            'competitor_rows': rows[start : start + cls.COMPETITOR_PAGE_SIZE],
            'competitor_page': page,
            'competitor_pages': pages,
            'competitor_page_start': start,
        }

    @classmethod
    def _ranking_rows(cls, championship: Championship, ranking=None, draggable=False):
        ranking = championship.ranking if ranking is None else ranking
        primary_rule = championship.rules[0] if championship.rules else None
        ranked_competitors = [entry.competitor for entry in ranking]
        # Carries the rule chain so best-stage selection ties are broken the
        # same way the ranking itself breaks them.
        selection_context = ScoringContext(
            ranked_competitors,
            championship.team_score_basis,
            rules=championship.rules,
        )
        stage_rules = cls._stage_rules(championship)
        ranked_competitor_ids = {id(competitor) for competitor in ranked_competitors}
        competitors = [
            competitor
            for competitor in championship.competitors
            if id(competitor) in ranked_competitor_ids
        ]
        # Which pre-manual tie group each competitor belongs to, so the ranking
        # can be dragged within those groups when a manual tie-break is used.
        manual_group_by_key: dict[str, int] = {}
        manual_group_size: dict[str, int] = {}
        manual_positions = championship.manual_positions
        if draggable and championship.has_manual_rule:
            for index, group in enumerate(
                championship.manual_tie_groups(ranked_competitors)
            ):
                for competitor in group:
                    manual_group_by_key[competitor.key] = index
                    manual_group_size[competitor.key] = len(group)
        rule_cells_by_competitor = cls._ranking_rule_cells(championship, competitors)
        rows = []
        for entry in ranking:
            competitor = entry.competitor
            category = ''
            gender = ''
            federation = ''
            if championship.competitor_type == ChampionshipCompetitorType.TEAM:
                name = competitor.name
                # Federation has its own column, so it is not repeated inline.
                secondary = ''
                federation = competitor.federation
            else:
                name = f'{competitor.last_name}, {competitor.first_name}'
                secondary = str(competitor.fide_id or '')
                category = championship.player_age_category(competitor)
                genders: list[str] = []
                federations: list[str] = []
                for participation in competitor.participations:
                    source_player = getattr(participation, 'tournament_player', None)
                    gender_name = getattr(
                        getattr(source_player, 'gender', None), 'short_name', ''
                    )
                    if gender_name and gender_name not in genders:
                        genders.append(gender_name)
                    federation_name = getattr(
                        getattr(source_player, 'federation', None), 'name', ''
                    )
                    if federation_name and federation_name not in federations:
                        federations.append(federation_name)
                gender = ' / '.join(genders)
                federation = ' / '.join(federations)
            counted_participations = (
                best_participations(
                    competitor,
                    getattr(primary_rule, 'best_n', None),
                    championship.team_score_basis,
                    selection_context,
                )
                if not isinstance(primary_rule, DirectEncounterRule)
                else competitor.participations
            )
            counted_participation_ids = {
                id(participation) for participation in counted_participations
            }
            # Stages best-first by the configured rule chain, each with its value.
            ordered_participations = best_participations(
                competitor,
                None,
                championship.team_score_basis,
                selection_context,
            )
            stages = []
            for participation in ordered_participations:
                # Reconciliation only keeps participations whose source resolved.
                tournament = participation.source.tournament
                assert tournament is not None
                if championship.competitor_type == ChampionshipCompetitorType.TEAM:
                    competitor_count = tournament.team_count
                else:
                    competitor_count = tournament.player_count
                competitor_ranking = participation.rank
                stages.append(
                    {
                        'name': participation.source.tournament_name,
                        'competitor_count': competitor_count,
                        'competitor_ranking': competitor_ranking,
                        'rule_values': [
                            rule.stage_display(participation, selection_context) or '—'
                            for rule in stage_rules
                        ],
                        'counted': id(participation) in counted_participation_ids,
                    }
                )
            used_stages = [stage for stage in stages if stage['counted']]
            rows.append(
                {
                    'rank': entry.rank,
                    'tied': entry.tied,
                    'name': name,
                    'secondary': secondary,
                    'category': category,
                    'gender': gender,
                    'federation': federation,
                    'rule_cells': rule_cells_by_competitor[id(competitor)],
                    'stages': stages,
                    'used_stage_count': len(used_stages),
                    'stage_count': len(stages),
                    'used_stage_names': [stage['name'] for stage in used_stages],
                    'competitor_key': competitor.key,
                    'manual_group': manual_group_by_key.get(competitor.key),
                    'manual_draggable': manual_group_size.get(competitor.key, 1) > 1,
                    'manual_pinned': competitor.key in manual_positions,
                }
            )
        return rows

    @staticmethod
    def _ranking_rule_cells(
        championship: Championship, competitors: list[Any]
    ) -> dict[int, list[dict[str, Any]]]:
        """Calculate display values for every configured rule.

        Ranking rules only refine competitors that remain tied. Later scalar
        values are still useful context, so they are included with ``used``
        false once an earlier rule has already separated that competitor.
        """
        cells_by_competitor: dict[int, list[dict[str, Any]]] = {
            id(competitor): [] for competitor in competitors
        }
        if not competitors:
            return cells_by_competitor

        context = ScoringContext(
            competitors,
            championship.team_score_basis,
            rules=championship.rules,
        )
        final_positions = {
            id(competitor): position
            for position, competitor in enumerate(
                (
                    competitor
                    for group in rank_competitors(
                        competitors,
                        championship.rules,
                        championship.team_score_basis,
                    )
                    for competitor in group
                ),
                start=1,
            )
        }
        groups: list[list[Any]] = [competitors]
        for rule_index, rule in enumerate(championship.rules):
            rank_progress: dict[int, int] = {}
            if isinstance(rule, DirectEncounterRule):
                rules_without_direct_encounter = [
                    other_rule
                    for other_index, other_rule in enumerate(championship.rules)
                    if other_index != rule_index
                ]
                positions_without_direct_encounter = {
                    id(competitor): position
                    for position, competitor in enumerate(
                        (
                            competitor
                            for group in rank_competitors(
                                competitors,
                                rules_without_direct_encounter,
                                championship.team_score_basis,
                            )
                            for competitor in group
                        ),
                        start=1,
                    )
                }
                rank_progress = {
                    competitor_id: position - final_positions[competitor_id]
                    for competitor_id, position in (
                        positions_without_direct_encounter.items()
                    )
                }
            refined_groups: list[list[Any]] = []
            for group in groups:
                still_tied = len(group) > 1
                ranges = (
                    rule.score_ranges(group, context)
                    if still_tied and isinstance(rule, DirectEncounterRule)
                    else None
                )
                scores = rule.scores(group, context) if ranges is None else None
                for competitor in group:
                    score_range = ranges[id(competitor)] if ranges is not None else None
                    cells_by_competitor[id(competitor)].append(
                        {
                            'value': (
                                None
                                if isinstance(rule, DirectEncounterRule)
                                else (
                                    scores[id(competitor)]
                                    if scores is not None
                                    else None
                                )
                            ),
                            'rank_progress': (
                                rank_progress[id(competitor)]
                                if score_range is not None
                                else None
                            ),
                            'used': still_tied
                            and (ranges is not None or scores is not None),
                            'manual': isinstance(rule, ManualRule),
                        }
                    )
                refined_groups.extend(
                    rule.split(group, context) if still_tied else [group]
                )
            groups = refined_groups
        return cells_by_competitor

    @staticmethod
    @staticmethod
    def _aggregatable_tie_breaks(championship: Championship) -> list:
        """The tie-breaks a Σ/ø rule may aggregate, instantiated with defaults and
        filtered to the championship's competitor type. Any tie-break can be
        COMPUTED from each stage's games, so the picker offers the full set
        available across the sources — not only the ones the sources happen to
        have been configured with.

        Rating-based tie-breaks (performance, average opponent rating, …) are
        excluded: a rating is per-event and not carried at the championship level,
        so aggregating them across stages is not meaningful."""
        is_team = championship.competitor_type == ChampionshipCompetitorType.TEAM
        tie_breaks = []
        for tie_break_class in aggregatable_tie_break_types(championship.sources):
            tie_break = tie_break_class()
            if not tie_break.allow_unrated_players:
                continue
            if is_team:
                if not tie_break.supports_team_mode:
                    continue
            elif tie_break.is_team_tiebreak:
                continue
            tie_breaks.append(tie_break)
        return tie_breaks

    @staticmethod
    def _source_tie_break_type_ids(championship: Championship) -> set[str]:
        """The tie-break type ids actually configured in the source tournaments,
        used to surface those tie-breaks first in the picker."""
        type_ids: set[str] = set()
        for source in championship.sources:
            tournament = source.tournament
            if tournament is None:
                continue
            for stored_tie_break in tournament.stored_tournament.stored_tie_breaks:
                type_ids.add(stored_tie_break.type)
        return type_ids

    @staticmethod
    def _tie_break_option_objects(tie_breaks: list) -> list:
        """The union of the offered tie-breaks' options, one instance per option
        id, so the modal renders each option field once (shown for the types that
        use it, mirroring the event tie-break picker)."""
        options: dict[str, Any] = {}
        for tie_break in tie_breaks:
            for option in tie_break.default_options():
                options.setdefault(option.id, option)
        return list(options.values())

    @classmethod
    def _tie_break_from_data(cls, championship: Championship, data: dict[str, str]):
        """Rebuild the configured tie-break from the posted type + option fields,
        or ``None`` if no valid type was chosen."""
        types_by_id = {
            tie_break.id: type(tie_break)
            for tie_break in cls._aggregatable_tie_breaks(championship)
        }
        type_id = WebContext.form_data_to_str(data, 'tie_break_type') or ''
        tie_break_class = types_by_id.get(type_id)
        if tie_break_class is None:
            return None
        options = []
        for option in tie_break_class().default_options():
            value = WebContext.form_data_to_value(data, option.id, option.type)
            options.append(type(option)(value))
        return tie_break_class(options)

    @staticmethod
    def _rule_header(rule) -> dict:
        """Results column header for a rule: the short acronym plus a full
        label/description tooltip (acronyms keep the table narrow)."""
        label = rule.label()
        best_n = getattr(rule, 'best_n', None)
        if best_n:
            label = _('{label} (best {num} stages)').format(label=label, num=best_n)
        description = rule.description()
        if isinstance(rule, F1PointsRule):
            description = _(
                'Points awarded per finishing position: {table}. '
                'Positions beyond the table score nothing.'
            ).format(table=' '.join(f'{point:g}' for point in rule.table))
        return {
            'acronym': rule.acronym,
            'title': label,
            'description': description,
        }

    @staticmethod
    def _rule_select_options() -> dict[str, SelectOption]:
        """Rule-type picker options, each with a description tooltip."""
        return {
            rule_class.static_id(): SelectOption(
                name=rule_class.label(), tooltip=rule_class.description()
            )
            for rule_class in championship_rules()
        }

    @staticmethod
    def _config_container_id(config_template: str) -> str:
        """The modal container id for a rule's options fragment, derived from the
        fragment name so rules sharing a fragment (the two tie-break rules) share
        one container rather than rendering it — and its element ids — twice."""
        return 'rule-config-' + PurePosixPath(config_template).stem

    @classmethod
    def _rule_config_templates(cls) -> list[dict[str, str]]:
        """The distinct rule-option fragments to render in the modal, each with
        the container id that shows/hides it."""
        templates: list[dict[str, str]] = []
        seen: set[str] = set()
        for rule_class in championship_rules():
            if not rule_class.config_template:
                continue
            container_id = cls._config_container_id(rule_class.config_template)
            if container_id in seen:
                continue
            seen.add(container_id)
            templates.append(
                {'container_id': container_id, 'template': rule_class.config_template}
            )
        return templates

    @classmethod
    def _rule_containers_by_type(cls) -> dict[str, list[str]]:
        """Which field containers each rule type shows in the modal: the generic
        best-N and coefficient fields plus the rule's own options fragment."""
        containers: dict[str, list[str]] = {}
        for rule_class in championship_rules():
            fields: list[str] = []
            if rule_class.supports_best_n:
                fields.append('rule-best-n')
            if rule_class.config_template:
                fields.append(cls._config_container_id(rule_class.config_template))
            if rule_class.uses_coefficient:
                fields.append('rule-coefficient')
            containers[rule_class.static_id()] = fields
        return containers

    @classmethod
    def _rule_display(cls, stored_rule: StoredChampionshipRule) -> dict[str, Any]:
        """Read-only summary of a stored rule for the configuration row. The
        rule-specific details come from the rule class; best-N and the
        coefficient toggle are common to every rule."""
        rule = build_rule(stored_rule.type, stored_rule.best_n, stored_rule.options)
        options = stored_rule.options or {}
        details: list[str] = []
        if stored_rule.best_n:
            details.append(_('best {num} stages').format(num=stored_rule.best_n))
        details.extend(type(rule).display_details(options))
        if type(rule).uses_coefficient and not options.get('use_coefficient', True):
            details.append(_('coefficient off'))
        return {
            'id': stored_rule.id,
            'name': rule.label(),
            'acronym': rule.acronym,
            'details': ' · '.join(details),
        }

    @staticmethod
    def _rule_form_data(stored_rule: StoredChampionshipRule | None) -> dict[str, str]:
        """Initial modal form values for a rule (defaults when creating). The
        rule-specific fields come from the rule class."""
        if stored_rule is None:
            return {'type': TotalPointsRule.static_id(), 'use_coefficient': 'on'}
        options = stored_rule.options or {}
        data = {
            'type': stored_rule.type,
            'best_n': str(stored_rule.best_n) if stored_rule.best_n else '',
            'use_coefficient': 'on' if options.get('use_coefficient', True) else '',
        }
        rule_class = championship_rule_class(stored_rule.type)
        data |= rule_class.config_form_data(options)
        return data

    @classmethod
    def _parse_rule_form(
        cls,
        championship: Championship,
        data: dict[str, str],
    ) -> tuple[tuple[str, int | None, dict] | None, dict[str, str]]:
        """Parse the rule modal form into ``(type, best_n, options)`` or errors."""
        errors: dict[str, str] = {}
        rule_type = WebContext.form_data_to_str(data, 'type') or ''
        try:
            rule_class = championship_rule_class(rule_type)
        except ValueError:
            return None, {'type': _('Please select a rule.')}
        best_n: int | None = None
        if rule_class.supports_best_n:
            best_text = (WebContext.form_data_to_str(data, 'best_n') or '').strip()
            if best_text:
                try:
                    best_n = int(best_text)
                    if best_n < 1:
                        raise ValueError
                except ValueError:
                    errors['best_n'] = _('Please enter a whole number of 1 or more.')
        options: dict[str, Any] = {}
        if rule_class.static_id() in ('SUM_TIE_BREAK', 'AVERAGE_TIE_BREAK'):
            # A tie-break rule's options depend on the championship's available
            # tie-breaks, so it is resolved here rather than by the rule class.
            tie_break = cls._tie_break_from_data(championship, data)
            if tie_break is None:
                errors['tie_break_type'] = _('Please choose a tie-break.')
            else:
                try:
                    tie_break.validate_options()
                except OptionError as error:
                    errors[error.option.id] = str(error)
                else:
                    stored = tie_break.to_stored_value()
                    options['tie_break'] = {
                        'type': stored.type,
                        'options': stored.options,
                        'acronym': tie_break.acronym,
                    }
        else:
            rule_options, rule_errors = rule_class.parse_config(data)
            options.update(rule_options)
            errors.update(rule_errors)
        if rule_class.uses_coefficient:
            options['use_coefficient'] = WebContext.form_data_to_bool(
                data, 'use_coefficient'
            )
        if errors:
            return None, errors
        return (rule_class.static_id(), best_n, options), {}

    @staticmethod
    def _stored_rule(
        championship: Championship, rule_id: int
    ) -> StoredChampionshipRule:
        rule = next(
            (
                rule
                for rule in championship.stored_championship.stored_championship_rules
                if rule.id == rule_id
            ),
            None,
        )
        if rule is None:
            raise NotFoundException(f'Championship rule [{rule_id}] not found')
        return rule

    @classmethod
    def _render_rule_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        rule: StoredChampionshipRule | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        tie_breaks = cls._aggregatable_tie_breaks(championship)
        option_objects = cls._tie_break_option_objects(tie_breaks)
        source_type_ids = cls._source_tie_break_type_ids(championship)

        def option_for(tie_break) -> SelectOption:
            return SelectOption(
                name=f'{tie_break.picker_acronym} - {tie_break.name}',
                tooltip=tie_break.picker_help_text,
            )

        tie_break_type_options: dict[str, Any] = {'': _('Choose a tie-break…')}
        # Tie-breaks configured in the source tournaments come first, as a shortcut
        # group; the rest follow grouped by category.
        used = {
            tie_break.id: option_for(tie_break)
            for tie_break in tie_breaks
            if tie_break.id in source_type_ids
        }
        if used:
            tie_break_type_options[_('Used in the source tournaments')] = used
        grouped: dict[str, dict[str, SelectOption]] = defaultdict(dict)
        for tie_break in tie_breaks:
            if tie_break.id in source_type_ids:
                continue
            grouped[tie_break.category.name][tie_break.id] = option_for(tie_break)
        tie_break_type_options |= dict(grouped)
        # Defaults for every option field, plus an empty type, so the round-trip
        # and the show/hide logic always have a value to read.
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in option_objects
        } | {'tie_break_type': ''}
        form_data = data if data is not None else cls._rule_form_data(rule)
        representative = next(
            (source for source in championship.sources if not source.broken), None
        )
        rule_containers_by_type = cls._rule_containers_by_type()
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'rule': rule,
            'data': default_data | form_data,
            'errors': errors or {},
            'rule_select_options': cls._rule_select_options(),
            'rule_containers_by_type': rule_containers_by_type,
            'rule_config_templates': cls._rule_config_templates(),
            'all_rule_container_ids': sorted(
                {cid for ids in rule_containers_by_type.values() for cid in ids}
            ),
            'tie_break_type_options': tie_break_type_options,
            'tie_break_options': option_objects,
            'tie_break_containers_by_type': {
                tie_break.id: [
                    option.container_id for option in tie_break.default_options()
                ]
                for tie_break in tie_breaks
            }
            | {'': []},
            # The option fragments are shared with the event tie-break modal and
            # read the tournament/event (pairing system, rounds, and whatever a
            # plugin's option needs). A championship has no tournament of its own,
            # so a resolved source stands in — real objects satisfy any attribute
            # the fragments (including plugin ones) reach for.
            'admin_tournament': representative.tournament if representative else None,
            'admin_event': representative.event if representative else None,
            'f1_default_points': ' '.join(f'{point:g}' for point in DEFAULT_F1_POINTS),
        }
        return cls._render_modal('admin/championship/rule_modal.html', context)

    @classmethod
    def _render(
        cls,
        request: HTMXRequest,
        championship_uniq_id: str,
        championship_tab: ChampionshipTab,
    ) -> Template:
        championship = cls._load_championship(championship_uniq_id)
        if championship_tab not in (
            'sources',
            'competitors',
            'configuration',
            'results',
        ):
            raise NotFoundException(f'Invalid Championship tab [{championship_tab}]')
        web_context = AdminWebContext(request)
        is_team = championship.competitor_type == ChampionshipCompetitorType.TEAM
        competitor_count = len(championship.competitors) or '-'
        if is_team:
            competitor_nav = {
                'title': _('Teams ({num})').format(num=competitor_count),
                'icon_class': 'bi-people-fill',
            }
        else:
            competitor_nav = {
                'title': _('Players ({num}) *** WITH_SHORTCUT_INDICATION').format(
                    num=competitor_count
                ),
                'icon_class': 'bi-people-fill',
                'shortcut': f'{_("*** KEYBOARD SHORTCUT FOR THE PLAYERS TAB")} from:body',
            }
        nav_tabs = {
            'configuration': {
                'title': _('Configuration *** WITH_SHORTCUT_INDICATION'),
                'icon_class': 'bi-gear-fill',
                'shortcut': f'{_("*** KEYBOARD SHORTCUT FOR THE CONFIGURATION TAB")} from:body',
            },
            'sources': {
                'title': _('Sources *** WITH_SHORTCUT_INDICATION'),
                'icon_class': 'bi-diagram-3-fill',
                'shortcut': f'{_("*** KEYBOARD SHORTCUT FOR THE SOURCES TAB")} from:body',
            },
            'competitors': competitor_nav,
            'results': {
                'title': _('Rankings *** WITH_SHORTCUT_INDICATION'),
                'icon_class': 'bi-trophy-fill',
                'shortcut': f'{_("*** KEYBOARD SHORTCUT FOR THE RANKINGS TAB")} from:body',
            },
        }
        context = web_context.template_context | {
            'messages': Message.messages(request),
            'championship': championship,
            'championship_tab': championship_tab,
            'nav_tabs': nav_tabs,
            'score': cls._score,
            'format_date': format_date,
            'competitor_type_individual': ChampionshipCompetitorType.INDIVIDUAL,
            'competitor_type_team': ChampionshipCompetitorType.TEAM,
            'rule_types': championship_rules(),
            'team_score_bases': TeamScoreBasis,
        }
        if championship_tab == 'sources':
            context['source_events'] = cls._source_events(championship)
        elif championship_tab == 'competitors':
            context.update(cls._competitor_page_context(championship, 1))
        elif championship_tab == 'configuration':
            context['rule_displays'] = [
                cls._rule_display(stored_rule)
                for stored_rule in sorted(
                    championship.stored_championship.stored_championship_rules,
                    key=lambda stored_rule: stored_rule.index,
                )
            ]
            context['age_category_data'] = WebContext.values_dict_to_form_data(
                {'age_category_base_date': championship.age_category_base_date}
            )
            context['category_criteria_labels'] = {
                category.id: [
                    cls._criterion_label(criterion)
                    for criterion in category.stored_category.stored_criteria
                ]
                for category in championship.categories
            }
        elif championship_tab == 'results':
            context['ranking_rule_labels'] = [
                cls._rule_header(rule) for rule in championship.rules
            ]
            context['stage_value_headers'] = [
                {'acronym': rule.stage_metric, 'title': rule.label()}
                for rule in cls._stage_rules(championship)
            ]
            context['has_manual_rule'] = championship.has_manual_rule
            context['has_manual_values'] = bool(championship.manual_positions)
            context['ranking_rows'] = cls._ranking_rows(championship, draggable=True)
            context['category_rankings'] = [
                {
                    'category': category,
                    'rows': cls._ranking_rows(championship, category.ranking),
                }
                for category in championship.categories
            ]
        return HTMXTemplate(
            template_name='admin/championship/layout.html', context=context
        )

    @classmethod
    def _render_create_modal(
        cls,
        request: HTMXRequest,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        context = AdminWebContext(
            request, admin_tab='championships'
        ).template_context | {
            'data': data
            or {
                'name': '',
                'competitor_type': ChampionshipCompetitorType.INDIVIDUAL.value,
            },
            'errors': errors or {},
        }
        return cls._render_modal('admin/championship/create_modal.html', context)

    @classmethod
    def _render_source_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        previous_source=None,
    ) -> Template:
        data = data or {'event_uniq_id': '', 'tournament_id': ''}
        source_events = cls._source_events(championship)
        event_options: dict[str, str] = {'': _('Select an event…')}
        for event in source_events:
            event_options[event['uniq_id']] = event['name']
        selected_event = next(
            (
                event
                for event in source_events
                if event['uniq_id'] == data.get('event_uniq_id')
            ),
            None,
        )
        tournament_options: dict[str, str] = {'': _('Select a tournament stage…')}
        if selected_event is not None:
            tournaments = selected_event['tournaments']
            for tournament in tournaments:
                tournament_options[str(tournament['id'])] = '{name} ({date})'.format(
                    name=tournament['name'],
                    date=format_date(tournament['start_date']),
                )
            # A single available stage is pre-selected as a convenience.
            if len(tournaments) == 1 and not data.get('tournament_id'):
                data = data | {'tournament_id': str(tournaments[0]['id'])}
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'source_events': source_events,
            'event_options': event_options,
            'tournament_options': tournament_options,
            'tournament_disabled': selected_event is None,
            'data': data,
            'errors': errors or {},
            'previous_source': previous_source,
            'add_other_active': SessionChampionshipSourcesAddOtherActive(request).get(),
            'format_date': format_date,
        }
        return cls._render_modal('admin/championship/source_modal.html', context)

    @staticmethod
    def _stored_category(
        championship: Championship, category_id: int
    ) -> StoredChampionshipCategory:
        category = next(
            (
                category
                for category in championship.stored_championship.stored_championship_categories
                if category.id == category_id
            ),
            None,
        )
        if category is None:
            raise NotFoundException(f'Championship category [{category_id}] not found')
        return category

    @staticmethod
    def _source(championship: Championship, source_id: int) -> ChampionshipSource:
        source = next(
            (source for source in championship.sources if source.id == source_id), None
        )
        if source is None:
            raise NotFoundException(f'Championship source [{source_id}] not found')
        return source

    @staticmethod
    def _stored_criterion(
        category: StoredChampionshipCategory, criterion_id: int
    ) -> StoredChampionshipCriterion:
        criterion = next(
            (
                criterion
                for criterion in category.stored_criteria
                if criterion.id == criterion_id
            ),
            None,
        )
        if criterion is None:
            raise NotFoundException(
                f'Championship criterion [{criterion_id}] not found'
            )
        return criterion

    @staticmethod
    def _criterion_label(criterion: StoredChampionshipCriterion) -> str:
        if criterion.type == 'AGE':
            return _('Age: {minimum} – {maximum}').format(
                minimum=criterion.options.get('MIN_AGE_CATEGORY') or '…',
                maximum=criterion.options.get('MAX_AGE_CATEGORY') or '…',
            )
        if criterion.type == 'GENDER':
            return _('Gender: {gender}').format(
                gender=(
                    _('Women')
                    if criterion.options.get('GENDER_VALUE') == PlayerGender.WOMAN.value
                    else _('Men')
                )
            )
        return criterion.type

    @classmethod
    def _render_category_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        previous_category: StoredChampionshipCategory | None = None,
    ) -> Template:
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'data': data or {'name': ''},
            'errors': errors or {},
            'previous_category': previous_category,
            'add_other_active': SessionChampionshipCategoriesAddOtherActive(
                request
            ).get(),
        }
        return cls._render_modal('admin/championship/category_modal.html', context)

    @classmethod
    def _render_category_rename_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        category: StoredChampionshipCategory,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> Template:
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'category': category,
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal(
            'admin/championship/category_rename_modal.html', context
        )

    @classmethod
    def _render_coefficient_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        source: ChampionshipSource,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> Template:
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'source': source,
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal(
            'admin/championship/source_coefficient_modal.html', context
        )

    @classmethod
    def _render_criteria_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        category: StoredChampionshipCategory,
    ) -> Template:
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'category': category,
            'criterion_labels': {
                criterion.id: cls._criterion_label(criterion)
                for criterion in category.stored_criteria
            },
        }
        return cls._render_modal('admin/championship/criteria_modal.html', context)

    @classmethod
    def _render_criterion_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        category: StoredChampionshipCategory,
        criterion: StoredChampionshipCriterion | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        previous_criterion: StoredChampionshipCriterion | None = None,
    ) -> Template:
        player_filters = [
            filter_type() for filter_type in CHAMPIONSHIP_PLAYER_FILTER_TYPES
        ]
        player_filter_options = [
            option
            for player_filter in player_filters
            for option in player_filter.default_options()
        ]
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in player_filter_options
        } | {'type': ''}
        if data is None:
            data = default_data.copy()
            if criterion:
                data['type'] = criterion.type
                data.update(
                    {
                        option_id: WebContext.value_to_form_data(value)
                        for option_id, value in criterion.options.items()
                    }
                )
        else:
            data = default_data | data
        used_types = {
            stored_criterion.type
            for stored_criterion in category.stored_criteria
            if criterion is None or stored_criterion.id != criterion.id
        }
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'category': category,
            'criterion': criterion,
            'player_filter_select_options': {'': '—'}
            | {
                player_filter.id: player_filter.name
                for player_filter in player_filters
                if player_filter.id not in used_types
            },
            'player_filter_options': player_filter_options,
            'containers_by_type': {
                player_filter.id: [
                    option.container_id for option in player_filter.default_options()
                ]
                for player_filter in player_filters
            }
            | {'': []},
            'player_filter_option_select_options': {
                'MIN_AGE_CATEGORY': {'': '—'}
                | {
                    category.id: category.name
                    for category in (
                        SELECTABLE_JUNIOR_CATEGORIES + SELECTABLE_SENIOR_CATEGORIES
                    )
                },
                'MAX_AGE_CATEGORY': {'': '—'}
                | {
                    category.id: category.name
                    for category in (
                        SELECTABLE_JUNIOR_CATEGORIES + SELECTABLE_SENIOR_CATEGORIES
                    )
                },
                'GENDER_VALUE': {
                    gender.value: gender.name
                    for gender in (PlayerGender.WOMAN, PlayerGender.MAN)
                },
            },
            'data': data,
            'errors': errors or {},
            'previous_criterion': previous_criterion,
            'previous_criterion_label': (
                cls._criterion_label(previous_criterion) if previous_criterion else None
            ),
            'add_other_active': SessionChampionshipCriteriaAddOtherActive(
                request
            ).get(),
        }
        return cls._render_modal('admin/championship/criterion_modal.html', context)

    @staticmethod
    def _criterion_from_data(
        data: dict[str, str],
    ) -> tuple[StoredChampionshipCriterion | None, dict[str, str]]:
        errors: dict[str, str] = {}
        criterion_type = WebContext.form_data_to_str(data, 'type') or ''
        filter_types = {
            filter_type.static_id(): filter_type
            for filter_type in CHAMPIONSHIP_PLAYER_FILTER_TYPES
        }
        if criterion_type not in filter_types:
            errors['type'] = _('Please select a type of criterion.')
            return None, errors
        filter_type = filter_types[criterion_type]
        options = []
        for default_option in filter_type().default_options():
            try:
                value = WebContext.form_data_to_value(
                    data, default_option.id, default_option.type
                )
            except ValueError:
                errors[default_option.id] = _('Please enter a valid value.')
                continue
            options.append(type(default_option)(value))
        if errors:
            return None, errors
        player_filter = filter_type(options)
        try:
            player_filter.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
            return None, errors
        return (
            StoredChampionshipCriterion(
                id=None,
                type=criterion_type,
                options={option.id: option.value for option in player_filter.options},
            ),
            {},
        )

    @get(
        path='/championship/{championship_uniq_id:str}/{championship_tab:str}',
        name='admin-championship-tab',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_tab(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        championship_tab: FromPath[ChampionshipTab],
    ) -> Template:
        return self._render(request, championship_uniq_id, championship_tab)

    @get(
        path='/championship-create-modal',
        name='admin-championship-create-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_create_modal(
        self, request: HTMXRequest
    ) -> Template:
        return self._render_create_modal(request)

    @post(
        path='/championship-create',
        name='admin-championship-create',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | ClientRedirect:
        name = (WebContext.form_data_to_str(data, 'name') or '').strip()
        errors: dict[str, str] = {}
        if not name:
            errors['name'] = _('Please enter a name for the championship.')
        try:
            competitor_type = ChampionshipCompetitorType(
                WebContext.form_data_to_str(data, 'competitor_type') or ''
            )
        except ValueError:
            competitor_type = ChampionshipCompetitorType.INDIVIDUAL
            errors['competitor_type'] = _('Please select a competitor type.')
        if errors:
            return self._render_create_modal(request, data, errors)
        uniq_id = ChampionshipLoader().create_championship(name, competitor_type.value)
        ChampionshipLoader().set_championship_rules(
            uniq_id, [(TotalPointsRule.static_id(), None)]
        )
        Message.success(
            request, _('Championship [{name}] has been created.').format(name=name)
        )
        return ClientRedirect(
            redirect_to=request.app.route_reverse(
                'admin-championship-tab',
                championship_uniq_id=uniq_id,
                championship_tab='configuration',
            )
        )

    @get(
        path='/championship-delete-modal/{championship_uniq_id:str}',
        name='admin-championship-delete-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_delete_modal(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'messages': Message.messages(request),
        }
        return self._render_modal('admin/championship/delete_modal.html', context)

    @delete(
        path='/championship-delete/{championship_uniq_id:str}',
        name='admin-championship-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_delete(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        archive = ChampionshipLoader().archive_championship(championship_uniq_id)
        Message.success(
            request,
            _('Championship [{name}] has been archived ({archive}).').format(
                name=championship.name,
                archive=archive,
            ),
        )
        return IndexAdminController._admin_render(
            AdminWebContext(request, admin_tab='championship_archives')
        )

    @post(
        path='/championship-archive/{archive_name:str}/restore',
        name='admin-championship-archive-restore',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_archive_restore(
        self, request: HTMXRequest, archive_name: FromPath[str]
    ) -> Template:
        archive = ChampionshipArchiveLoader.get_archive(archive_name)
        if archive is None:
            raise NotFoundException(f'Championship archive [{archive_name}] not found')
        championship_name = archive.display_name
        uniq_id = archive.restore()
        if uniq_id is None:
            Message.error(
                request,
                _('Championship archive [{archive}] could not be restored.').format(
                    archive=archive.name
                ),
            )
        else:
            Message.success(
                request,
                _('Championship [{name}] has been restored.').format(
                    name=championship_name
                ),
            )
        return IndexAdminController._admin_render(
            AdminWebContext(
                request,
                admin_tab='championships'
                if uniq_id is not None
                else 'championship_archives',
            )
        )

    @delete(
        path='/championship-archive/{archive_name:str}',
        name='admin-championship-archive-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_archive_delete(
        self, request: HTMXRequest, archive_name: FromPath[str]
    ) -> Template:
        archive = ChampionshipArchiveLoader.get_archive(archive_name)
        if archive is None:
            raise NotFoundException(f'Championship archive [{archive_name}] not found')
        championship_name = archive.display_name
        archive.file.unlink()
        Message.success(
            request,
            _('Championship archive [{name}] has been permanently deleted.').format(
                name=championship_name
            ),
        )
        return IndexAdminController._admin_render(
            AdminWebContext(request, admin_tab='championship_archives')
        )

    @get(
        path='/championship/{championship_uniq_id:str}/source-modal',
        name='admin-championship-source-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_source_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        event_uniq_id: FromQuery[str] = '',
    ) -> Template:
        return self._render_source_modal(
            request,
            self._load_championship(championship_uniq_id),
            data={'event_uniq_id': event_uniq_id, 'tournament_id': ''}
            if event_uniq_id
            else None,
        )

    # -------------------------------------------------------------------------
    # Base configuration (name, unique id, age-category reference date)
    # -------------------------------------------------------------------------

    @classmethod
    def _render_config_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        if data is None:
            data = {
                'name': championship.name,
                'min_participation': str(championship.min_participation)
                if championship.min_participation
                else '',
            } | WebContext.values_dict_to_form_data(
                {'age_category_base_date': championship.age_category_base_date}
            )
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'championship_uniq_ids': ChampionshipLoader.all_championship_ids(),
            'competitor_type_individual': ChampionshipCompetitorType.INDIVIDUAL,
            'format_date': format_date,
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal('admin/championship/config_modal.html', context)

    @get(
        path='/championship/{championship_uniq_id:str}/config-modal',
        name='admin-championship-config-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_config_modal(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        return self._render_config_modal(
            request, self._load_championship(championship_uniq_id)
        )

    @patch(
        path='/championship/{championship_uniq_id:str}/uniq-id',
        name='admin-championship-uniq-id-update',
        guards=[ActionGuard(AuthAction.RENAME_EVENT)],
    )
    async def htmx_admin_championship_uniq_id_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> ClientRedirect:
        self._load_championship(championship_uniq_id)
        new_uniq_id = (WebContext.form_data_to_str(data, 'uniq_id') or '').strip()
        if (
            not new_uniq_id
            or not SharlyChessConfig.uniq_id_regex.match(new_uniq_id)
            or (
                new_uniq_id != championship_uniq_id
                and new_uniq_id in ChampionshipLoader.all_championship_ids()
            )
        ):
            # The inline form performs precise validation before submission.
            raise ClientException(f'Invalid Championship unique ID [{new_uniq_id}].')
        if new_uniq_id != championship_uniq_id:
            try:
                ChampionshipLoader().rename_championship(
                    championship_uniq_id, new_uniq_id
                )
            except PermissionError as error:
                raise ClientException(
                    f'Renaming the Championship database failed: {error}.'
                ) from error
            Message.success(
                request,
                _(
                    'Championship unique ID has been renamed from '
                    '[{old_uniq_id}] to [{new_uniq_id}].'
                ).format(
                    old_uniq_id=championship_uniq_id,
                    new_uniq_id=new_uniq_id,
                ),
            )
        return ClientRedirect(
            redirect_to=request.app.route_reverse(
                'admin-championship-tab',
                championship_uniq_id=new_uniq_id,
                championship_tab='configuration',
            )
        )

    @post(
        path='/championship/{championship_uniq_id:str}/config',
        name='admin-championship-config-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_config_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | ClientRedirect:
        championship = self._load_championship(championship_uniq_id)
        is_individual = (
            championship.competitor_type == ChampionshipCompetitorType.INDIVIDUAL
        )
        name = (WebContext.form_data_to_str(data, 'name') or '').strip()
        errors: dict[str, str] = {}
        if not name:
            errors['name'] = _('Please enter a name.')
        base_date = None
        if is_individual:
            try:
                base_date = WebContext.form_data_to_date(data, 'age_category_base_date')
            except FormError as error:
                errors['age_category_base_date'] = str(error)
        min_participation = 0
        try:
            min_participation = (
                WebContext.form_data_to_int(
                    data, 'min_participation', empty_value=0, minimum=0
                )
                or 0
            )
        except ValueError:
            errors['min_participation'] = _('Please enter a positive whole number.')
        if errors:
            return self._render_config_modal(
                request, championship, data=data, errors=errors
            )
        loader = ChampionshipLoader()
        loader.set_name(championship_uniq_id, name)
        loader.set_min_participation(championship_uniq_id, min_participation)
        if is_individual:
            loader.set_age_category_base_date(championship_uniq_id, base_date)
        Message.success(request, _('The configuration has been saved.'))
        return ClientRedirect(
            redirect_to=request.app.route_reverse(
                'admin-championship-tab',
                championship_uniq_id=championship_uniq_id,
                championship_tab='configuration',
            )
        )

    # -------------------------------------------------------------------------
    # Documents
    # -------------------------------------------------------------------------

    @classmethod
    def _render_documents_modal(
        cls,
        request: HTMXRequest,
        championship: Championship,
        data: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        document_types = championship_print_documents(championship)
        document_options = {
            document_type.static_id(): document_type.label(championship)
            for document_type in document_types
        }
        ranking_set_options = {
            ChampionshipRankingsPrintDocument.OVERALL_SET: _('Overall')
        } | {str(category.id): category.name for category in championship.categories}
        # Every option, rendered once; the picker shows only the containers of the
        # selected document (mirrors the event document picker).
        print_options: list[ChampionshipPrintOption] = []
        containers_by_document: dict[str, list[str]] = {}
        seen_option_ids: set[str] = set()
        for document_type in document_types:
            options = document_type(championship).default_options()
            containers_by_document[document_type.static_id()] = [
                option.container_id for option in options
            ]
            for option in options:
                if option.id not in seen_option_ids:
                    seen_option_ids.add(option.id)
                    print_options.append(option)
        first_document_id = (data or {}).get('document') or next(
            iter(document_options), ''
        )
        # Prefill each option's default (e.g. the auto naming choice) unless the
        # form already carries a value.
        defaults = {
            option.id: WebContext.value_to_form_data(option.value)
            for option in print_options
        }
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'document_options': document_options,
            'ranking_set_options': ranking_set_options,
            'print_options': print_options,
            'containers_by_document': containers_by_document,
            'current_document_container_ids': containers_by_document.get(
                first_document_id, []
            ),
            'data': defaults | (data or {}) | {'document': first_document_id},
            'errors': errors or {},
        }
        return cls._render_modal('admin/championship/documents_modal.html', context)

    @get(
        path='/championship/{championship_uniq_id:str}/documents-modal',
        name='admin-championship-documents-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_documents_modal(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        return self._render_documents_modal(
            request, self._load_championship(championship_uniq_id)
        )

    @post(
        path='/championship/{championship_uniq_id:str}/generate-document',
        name='admin-championship-generate-document',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_generate_document(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        flat_data = WebContext.flatten_list_data(data)
        document_id = WebContext.form_data_to_str(flat_data, 'document') or ''
        try:
            document_type = championship_print_document_type(document_id)
        except ValueError:
            return self._render_documents_modal(
                request,
                championship,
                data=flat_data,
                errors={'document': _('Please choose the document.')},
            )
        # Encode each option as id=value (list values already ';'-joined by
        # flatten_list_data); the view decodes it back through the option types.
        options = {
            option.id: flat_data[option.id]
            for option in document_type(championship).default_options()
            if flat_data.get(option.id)
        }
        return HTMXTemplate(
            template_name='common/alert.html',
            re_target='#document-success-message',
            re_swap='innerHTML',
            context={
                'type': 'success',
                'message': _(
                    'Document [{document}] has been generated in another tab.'
                ).format(document=document_type.label(championship)),
            },
            trigger_event='do_print_championship',
            after='receive',
            params={
                'championship_uniq_id': championship_uniq_id,
                'document': document_id,
                'options': options,
            },
        )

    @get(
        path='/championship-document-view/{championship_uniq_id:str}/{document:str}',
        name='championship-document-view',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_championship_document_view(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        document: FromPath[str],
        options: FromQuery[str | None] = None,
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        document_type = championship_print_document_type(document)
        option_data: dict[str, str] = {}
        if options:
            for pair in urllib.parse.unquote(options).split('|'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    option_data[key] = value
        print_options: list[ChampionshipPrintOption] = []
        for option in document_type(championship).default_options():
            option_value = WebContext.form_data_to_value(
                option_data, option.id, option.type
            )
            print_options.append(type(option)(championship, option_value))
        print_document = document_type(championship, print_options)
        context = {'document': print_document} | self._document_context(print_document)
        return StreamingHTMXTemplate(
            template_name=print_document.template_name, context=context
        )

    @classmethod
    def _document_context(cls, document) -> dict[str, Any]:
        championship = document.championship
        is_team = championship.competitor_type == ChampionshipCompetitorType.TEAM
        if isinstance(document, ChampionshipTournamentListPrintDocument):
            return cls._tournament_list_context(document)
        if isinstance(document, ChampionshipCompetitorListPrintDocument):
            return {
                'is_team': is_team,
                'competitor_rows': cls._competitor_rows(championship),
            }
        ranking_sets = []
        categories_by_id = {
            str(category.id): category for category in championship.categories
        }
        for set_id in document.selected_set_ids():
            if set_id == ChampionshipRankingsPrintDocument.OVERALL_SET:
                ranking_sets.append(
                    {'title': _('Overall'), 'rows': cls._ranking_rows(championship)}
                )
            elif set_id in categories_by_id:
                category = categories_by_id[set_id]
                ranking_sets.append(
                    {
                        'title': category.name,
                        'rows': cls._ranking_rows(championship, category.ranking),
                    }
                )
        return {
            'is_team': is_team,
            'score': cls._score,
            'rule_headers': [cls._rule_header(rule) for rule in championship.rules],
            'ranking_sets': ranking_sets,
            'include_popover': document.include_popover(),
            'stage_value_headers': [
                {'acronym': rule.stage_metric, 'title': rule.label()}
                for rule in cls._stage_rules(championship)
            ],
        }

    @classmethod
    def _tournament_list_context(
        cls, document: ChampionshipTournamentListPrintDocument
    ) -> dict[str, Any]:
        championship = document.championship
        name_mode = document.option_value(TournamentNamePrintOption)
        is_team = championship.competitor_type == ChampionshipCompetitorType.TEAM

        def display_name(source) -> str:
            if name_mode == TournamentNamePrintOption.EVENT:
                return source.event_name
            if name_mode == TournamentNamePrintOption.TOURNAMENT:
                return source.tournament_name
            return f'{source.event_name} — {source.tournament_name}'

        def competitor_count(source) -> int | None:
            tournament = source.tournament
            if tournament is None:
                return None
            return tournament.team_count if is_team else tournament.player_count

        played, upcoming = [], []
        for source in championship.sources:
            row = {
                'name': display_name(source),
                'event_name': source.event_name,
                'tournament_name': source.tournament_name,
                'start_date': source.start_date,
                'competitor_count': competitor_count(source),
            }
            # Upcoming = starts in the future (matches the home-page split);
            # undated or started sources are treated as played.
            if source.start_date is not None and date.today() < source.start_date:
                upcoming.append(row)
            else:
                played.append(row)
        return {
            'is_team': is_team,
            'format_date': format_date,
            'played_tournaments': played,
            'upcoming_tournaments': upcoming,
        }

    @post(
        path='/championship/{championship_uniq_id:str}/source',
        name='admin-championship-source-add',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_source_add(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        add_other = WebContext.resolve_add_other(
            data, SessionChampionshipSourcesAddOtherActive(request)
        )
        errors: dict[str, str] = {}
        event_uniq_id = WebContext.form_data_to_str(data, 'event_uniq_id') or ''
        tournament_id = WebContext.form_data_to_int(data, 'tournament_id')
        if not event_uniq_id:
            errors['event_uniq_id'] = _('Please select an event.')
        if tournament_id is None:
            errors['tournament_id'] = _('Please select a tournament.')
        if errors:
            return self._render_source_modal(request, championship, data, errors)
        assert tournament_id is not None
        try:
            stored_source = ChampionshipLoader().add_source(
                championship_uniq_id, event_uniq_id, tournament_id
            )
        except (ValueError, TypeError):
            errors['tournament_id'] = _('Please select a valid tournament.')
            return self._render_source_modal(request, championship, data, errors)

        championship = self._load_championship(championship_uniq_id)
        if add_other:
            previous_source = next(
                source
                for source in championship.sources
                if source.stored_source.id == stored_source.id
            )
            # Keep the just-used event selected when it still has stages left to
            # add, so successive stages of one event can be added quickly. If none
            # remain, the event drops out of the picker and the field falls empty.
            return self._render_source_modal(
                request,
                championship,
                data={'event_uniq_id': event_uniq_id, 'tournament_id': ''},
                previous_source=previous_source,
            )
        Message.success(request, _('The tournament has been added.'))
        return self._render(request, championship_uniq_id, 'sources')

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/source/{source_id:int}/delete-modal'
        ),
        name='admin-championship-source-delete-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_source_delete_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        source_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        source = next(
            (source for source in championship.sources if source.id == source_id), None
        )
        if source is None:
            raise NotFoundException(f'Championship source [{source_id}] not found')
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'source': source,
        }
        return self._render_modal(
            'admin/championship/source_delete_modal.html', context
        )

    @delete(
        path='/championship/{championship_uniq_id:str}/source/{source_id:int}',
        name='admin-championship-source-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_source_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        source_id: FromPath[int],
    ) -> Template:
        self._load_championship(championship_uniq_id)
        ChampionshipLoader().delete_source(championship_uniq_id, source_id)
        Message.success(request, _('The source has been removed.'))
        return self._render(request, championship_uniq_id, 'sources')

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/source/'
            '{source_id:int}/coefficient-modal'
        ),
        name='admin-championship-source-coefficient-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_source_coefficient_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        source_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        source = self._source(championship, source_id)
        return self._render_coefficient_modal(
            request,
            championship,
            source,
            {'coefficient': f'{source.coefficient:g}'},
        )

    @post(
        path='/championship/{championship_uniq_id:str}/source/{source_id:int}/coefficient',
        name='admin-championship-source-coefficient',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_source_coefficient(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        source_id: FromPath[int],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        source = self._source(championship, source_id)
        errors: dict[str, str] = {}
        coefficient: float | None = None
        try:
            coefficient = WebContext.form_data_to_float(data, 'coefficient', minimum=0)
        except ValueError:
            coefficient = None
        if coefficient is None or coefficient <= 0:
            errors['coefficient'] = _('Please enter a coefficient greater than zero.')
        if errors:
            return self._render_coefficient_modal(
                request, championship, source, data, errors
            )
        assert coefficient is not None
        ChampionshipLoader().set_source_coefficient(
            championship_uniq_id, source_id, coefficient
        )
        Message.success(request, _('The coefficient has been saved.'))
        return self._render(request, championship_uniq_id, 'sources')

    @post(
        path='/championship/{championship_uniq_id:str}/merge',
        name='admin-championship-merge',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_merge(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str | list[str]], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        raw_groups = data.get('groups', data.get('refs', []))
        if isinstance(raw_groups, str):
            raw_groups = [raw_groups]
        refs: list[tuple[str, int, int]] = []
        try:
            for raw_group in raw_groups:
                for raw_ref in raw_group.split(';'):
                    event_uniq_id, tournament_id, competitor_id = raw_ref.split('|')
                    refs.append((event_uniq_id, int(tournament_id), int(competitor_id)))
        except ValueError:
            refs = []
        competitor_name = (
            _('teams')
            if championship.competitor_type == ChampionshipCompetitorType.TEAM
            else _('players')
        )
        if len(raw_groups) < 2 or len(refs) < 2:
            Message.error(
                request,
                _('Select at least two {competitors} to merge.').format(
                    competitors=competitor_name
                ),
            )
        else:
            group_key = f'manual-{uuid4()}'
            if championship.competitor_type == ChampionshipCompetitorType.TEAM:
                ChampionshipLoader().merge_teams(championship_uniq_id, refs, group_key)
            else:
                ChampionshipLoader().merge_players(
                    championship_uniq_id, refs, group_key
                )
            Message.success(
                request,
                _('The selected {competitors} have been merged.').format(
                    competitors=competitor_name
                ),
            )
        return self._render(request, championship_uniq_id, 'competitors')

    @delete(
        path=(
            '/championship/{championship_uniq_id:str}/override/'
            '{event_uniq_id:str}/{tournament_id:int}/{competitor_id:int}'
        ),
        name='admin-championship-override-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_override_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        event_uniq_id: FromPath[str],
        tournament_id: FromPath[int],
        competitor_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        if championship.competitor_type == ChampionshipCompetitorType.TEAM:
            ChampionshipLoader().clear_team_override(
                championship_uniq_id, event_uniq_id, tournament_id, competitor_id
            )
        else:
            ChampionshipLoader().clear_player_override(
                championship_uniq_id, event_uniq_id, tournament_id, competitor_id
            )
        Message.success(request, _('The manual match has been cleared.'))
        return self._render(request, championship_uniq_id, 'competitors')

    @delete(
        path=(
            '/championship/{championship_uniq_id:str}/override-group/{group_key:str}'
        ),
        name='admin-championship-override-group-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_override_group_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        group_key: FromPath[str],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        if championship.competitor_type == ChampionshipCompetitorType.TEAM:
            ChampionshipLoader().clear_team_override_group(
                championship_uniq_id, group_key
            )
        else:
            ChampionshipLoader().clear_player_override_group(
                championship_uniq_id, group_key
            )
        Message.success(request, _('The competitors have been unmerged.'))
        return self._render(request, championship_uniq_id, 'competitors')

    @get(
        path='/championship/{championship_uniq_id:str}/competitor-page/{page:int}',
        name='admin-championship-competitors-page',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_competitors_page(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        page: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        context = (
            AdminWebContext(request).template_context
            | {
                'championship': championship,
                'competitor_type_individual': ChampionshipCompetitorType.INDIVIDUAL,
                'competitor_type_team': ChampionshipCompetitorType.TEAM,
            }
            | self._competitor_page_context(championship, page)
        )
        return HTMXTemplate(
            template_name='/admin/championship/competitors_page.html',
            context=context,
        )

    @get(
        path='/championship/{championship_uniq_id:str}/rule-modal',
        name='admin-championship-rule-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rule_modal(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        return self._render_rule_modal(
            request, self._load_championship(championship_uniq_id)
        )

    @get(
        path='/championship/{championship_uniq_id:str}/rule/{rule_id:int}/modal',
        name='admin-championship-rule-edit-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rule_edit_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        rule_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        return self._render_rule_modal(
            request, championship, self._stored_rule(championship, rule_id)
        )

    @post(
        path='/championship/{championship_uniq_id:str}/rule',
        name='admin-championship-rule-add',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rule_add(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        parsed, errors = self._parse_rule_form(championship, data)
        if parsed is None:
            return self._render_rule_modal(request, championship, None, data, errors)
        rule_type, best_n, options = parsed
        ChampionshipLoader().add_championship_rule(
            championship_uniq_id,
            StoredChampionshipRule(
                id=None, type=rule_type, best_n=best_n, options=options
            ),
        )
        return self._render(request, championship_uniq_id, 'configuration')

    @patch(
        path='/championship/{championship_uniq_id:str}/rule/{rule_id:int}',
        name='admin-championship-rule-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rule_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        rule_id: FromPath[int],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        stored_rule = self._stored_rule(championship, rule_id)
        parsed, errors = self._parse_rule_form(championship, data)
        if parsed is None:
            return self._render_rule_modal(
                request, championship, stored_rule, data, errors
            )
        stored_rule.type, stored_rule.best_n, stored_rule.options = parsed
        ChampionshipLoader().update_championship_rule(championship_uniq_id, stored_rule)
        Message.success(request, _('The rule has been saved.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @get(
        path='/championship/{championship_uniq_id:str}/rule/{rule_id:int}/delete-modal',
        name='admin-championship-rule-delete-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rule_delete_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        rule_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'rule': self._rule_display(self._stored_rule(championship, rule_id)),
        }
        return self._render_modal('admin/championship/rule_delete_modal.html', context)

    @delete(
        path='/championship/{championship_uniq_id:str}/rule/{rule_id:int}',
        name='admin-championship-rule-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_rule_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        rule_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        self._stored_rule(championship, rule_id)
        ChampionshipLoader().delete_championship_rule(championship_uniq_id, rule_id)
        Message.success(request, _('The rule has been deleted.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @patch(
        path='/championship/{championship_uniq_id:str}/rules/reorder',
        name='admin-championship-rules-reorder',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_rules_reorder(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, list[int]], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        ChampionshipLoader().reorder_championship_rules(
            championship_uniq_id, data.get('item', [])
        )
        return self._render(request, championship_uniq_id, 'configuration')

    @patch(
        path='/championship/{championship_uniq_id:str}/manual-tiebreak',
        name='admin-championship-manual-tiebreak-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_manual_tiebreak_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str | list[str]], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        raw = data.get('competitor', [])
        submitted = [raw] if isinstance(raw, str) else list(raw)
        submitted_index = {key: index for index, key in enumerate(submitted)}
        ranked = [entry.competitor for entry in championship.ranking]
        current_index = {
            competitor.key: index for index, competitor in enumerate(ranked)
        }
        updates: dict[str, int | None] = {}
        # Reassign positions only for the tie groups whose order actually changed.
        for group in championship.manual_tie_groups(ranked):
            if len(group) <= 1:
                continue
            keys = [competitor.key for competitor in group]
            current = sorted(keys, key=lambda key: current_index.get(key, 0))
            new = sorted(
                keys,
                key=lambda key: submitted_index.get(key, current_index.get(key, 0)),
            )
            if current == new:
                continue
            for index, key in enumerate(new):
                updates[key] = len(group) - index
        if updates:
            ChampionshipLoader().set_manual_tiebreaks(championship_uniq_id, updates)
        return self._render(request, championship_uniq_id, 'results')

    @post(
        path='/championship/{championship_uniq_id:str}/manual-tiebreak/reset',
        name='admin-championship-manual-tiebreak-reset',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_manual_tiebreak_reset(
        self, request: HTMXRequest, championship_uniq_id: FromPath[str]
    ) -> Template:
        self._load_championship(championship_uniq_id)
        ChampionshipLoader().reset_manual_tiebreaks(championship_uniq_id)
        Message.success(request, _('The manual tie-break has been reset.'))
        return self._render(request, championship_uniq_id, 'results')

    @post(
        path='/championship/{championship_uniq_id:str}/team-score-basis',
        name='admin-championship-team-score-basis-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_team_score_basis_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        try:
            ChampionshipLoader().set_team_score_basis(
                championship_uniq_id,
                WebContext.form_data_to_str(data, 'team_score_basis') or '',
            )
        except ValueError:
            Message.error(request, _('Please select a valid score basis.'))
        else:
            Message.success(request, _('The team score basis has been saved.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @post(
        path='/championship/{championship_uniq_id:str}/age-category-base-date',
        name='admin-championship-category-reference-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_reference_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        try:
            base_date = WebContext.form_data_to_date(data, 'age_category_base_date')
        except FormError as error:
            Message.error(request, str(error))
        else:
            ChampionshipLoader().set_age_category_base_date(
                championship_uniq_id, base_date
            )
        return self._render(request, championship_uniq_id, 'configuration')

    @get(
        path='/championship/{championship_uniq_id:str}/category-modal',
        name='admin-championship-category-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
    ) -> Template:
        return self._render_category_modal(
            request, self._load_championship(championship_uniq_id)
        )

    @post(
        path='/championship/{championship_uniq_id:str}/category',
        name='admin-championship-category-add',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_add(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        add_other = WebContext.resolve_add_other(
            data, SessionChampionshipCategoriesAddOtherActive(request)
        )
        errors: dict[str, str] = {}
        name = (WebContext.form_data_to_str(data, 'name') or '').strip()
        if not name:
            errors['name'] = _('Please enter a category name.')
        elif any(
            category.name.casefold() == name.casefold()
            for category in championship.stored_championship.stored_championship_categories
        ):
            errors['name'] = _('A category with this name already exists.')
        if errors:
            return self._render_category_modal(request, championship, data, errors)
        category = ChampionshipLoader().add_championship_category(
            championship_uniq_id,
            StoredChampionshipCategory(
                id=None,
                name=name,
                index=len(
                    championship.stored_championship.stored_championship_categories
                ),
            ),
        )
        if add_other:
            return self._render_category_modal(
                request,
                self._load_championship(championship_uniq_id),
                previous_category=category,
            )
        return self._render(request, championship_uniq_id, 'configuration')

    @post(
        path='/championship/{championship_uniq_id:str}/category/{category_id:int}/duplicate',
        name='admin-championship-category-duplicate',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_duplicate(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        source = self._stored_category(championship, category_id)
        categories = championship.stored_championship.stored_championship_categories
        existing_names = {category.name.casefold() for category in categories}
        name = _('{name} (copy)').format(name=source.name)
        index = 2
        while name.casefold() in existing_names:
            name = _('{name} (copy {num})').format(name=source.name, num=index)
            index += 1
        duplicate = StoredChampionshipCategory(
            id=None,
            name=name,
            index=len(categories),
            stored_criteria=[
                StoredChampionshipCriterion(
                    id=None,
                    championship_category_id=None,
                    type=criterion.type,
                    options=copy.deepcopy(criterion.options),
                )
                for criterion in source.stored_criteria
            ],
        )
        ChampionshipLoader().add_championship_category(championship_uniq_id, duplicate)
        Message.success(request, _('The category has been duplicated.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/category/'
            '{category_id:int}/rename-modal'
        ),
        name='admin-championship-category-rename-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_rename_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        return self._render_category_rename_modal(
            request, championship, category, {'name': category.name}
        )

    @post(
        path='/championship/{championship_uniq_id:str}/category/{category_id:int}/rename',
        name='admin-championship-category-rename',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_rename(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        errors: dict[str, str] = {}
        name = (WebContext.form_data_to_str(data, 'name') or '').strip()
        if not name:
            errors['name'] = _('Please enter a category name.')
        elif any(
            other.id != category_id and other.name.casefold() == name.casefold()
            for other in championship.stored_championship.stored_championship_categories
        ):
            errors['name'] = _('A category with this name already exists.')
        if errors:
            return self._render_category_rename_modal(
                request, championship, category, data, errors
            )
        ChampionshipLoader().rename_championship_category(
            championship_uniq_id, category_id, name
        )
        Message.success(request, _('The category has been renamed.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @patch(
        path='/championship/{championship_uniq_id:str}/categories/reorder',
        name='admin-championship-categories-reorder',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_categories_reorder(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, list[int]], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        ChampionshipLoader().reorder_championship_categories(
            championship_uniq_id, data.get('item', [])
        )
        return self._render(request, championship_uniq_id, 'configuration')

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/category/'
            '{category_id:int}/delete-modal'
        ),
        name='admin-championship-category-delete-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_category_delete_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        context = AdminWebContext(request).template_context | {
            'championship': championship,
            'category': self._stored_category(championship, category_id),
        }
        return self._render_modal(
            'admin/championship/category_delete_modal.html', context
        )

    @delete(
        path='/championship/{championship_uniq_id:str}/category/{category_id:int}',
        name='admin-championship-category-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_category_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        self._stored_category(championship, category_id)
        ChampionshipLoader().delete_championship_category(
            championship_uniq_id, category_id
        )
        Message.success(request, _('The category has been deleted.'))
        return self._render(request, championship_uniq_id, 'configuration')

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/category/'
            '{category_id:int}/criteria-modal'
        ),
        name='admin-championship-criteria-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_criteria_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        return self._render_criteria_modal(
            request, championship, self._stored_category(championship, category_id)
        )

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/category/'
            '{category_id:int}/criterion-modal'
        ),
        name='admin-championship-criterion-create-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_criterion_create_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        return self._render_criterion_modal(
            request, championship, self._stored_category(championship, category_id)
        )

    @post(
        path=(
            '/championship/{championship_uniq_id:str}/category/{category_id:int}/criterion'
        ),
        name='admin-championship-criterion-add',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_criterion_add(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        add_other = WebContext.resolve_add_other(
            data, SessionChampionshipCriteriaAddOtherActive(request)
        )
        criterion, errors = self._criterion_from_data(data)
        criterion_type = WebContext.form_data_to_str(data, 'type') or ''
        if any(
            existing.type == criterion_type for existing in category.stored_criteria
        ):
            errors['type'] = _('This type of criterion is already defined.')
        if errors or criterion is None:
            return self._render_criterion_modal(
                request, championship, category, data=data, errors=errors
            )
        criterion.championship_category_id = category_id
        ChampionshipLoader().add_championship_criterion(championship_uniq_id, criterion)
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        if add_other:
            return self._render_criterion_modal(
                request,
                championship,
                category,
                previous_criterion=criterion,
            )
        return self._render_criteria_modal(request, championship, category)

    @get(
        path=(
            '/championship/{championship_uniq_id:str}/category/{category_id:int}/'
            'criterion/{criterion_id:int}/modal'
        ),
        name='admin-championship-criterion-update-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_criterion_update_modal(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
        criterion_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        return self._render_criterion_modal(
            request,
            championship,
            category,
            criterion=self._stored_criterion(category, criterion_id),
        )

    @patch(
        path=(
            '/championship/{championship_uniq_id:str}/category/{category_id:int}/'
            'criterion/{criterion_id:int}'
        ),
        name='admin-championship-criterion-update',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_championship_criterion_update(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
        criterion_id: FromPath[int],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        existing = self._stored_criterion(category, criterion_id)
        criterion, errors = self._criterion_from_data(data)
        criterion_type = WebContext.form_data_to_str(data, 'type') or ''
        if any(
            other.id != criterion_id and other.type == criterion_type
            for other in category.stored_criteria
        ):
            errors['type'] = _('This type of criterion is already defined.')
        if errors or criterion is None:
            return self._render_criterion_modal(
                request,
                championship,
                category,
                criterion=existing,
                data=data,
                errors=errors,
            )
        criterion.id = criterion_id
        criterion.championship_category_id = category_id
        ChampionshipLoader().update_championship_criterion(
            championship_uniq_id, criterion
        )
        championship = self._load_championship(championship_uniq_id)
        return self._render_criteria_modal(
            request,
            championship,
            self._stored_category(championship, category_id),
        )

    @delete(
        path=(
            '/championship/{championship_uniq_id:str}/category/{category_id:int}/'
            'criterion/{criterion_id:int}'
        ),
        name='admin-championship-criterion-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_championship_criterion_delete(
        self,
        request: HTMXRequest,
        championship_uniq_id: FromPath[str],
        category_id: FromPath[int],
        criterion_id: FromPath[int],
    ) -> Template:
        championship = self._load_championship(championship_uniq_id)
        category = self._stored_category(championship, category_id)
        self._stored_criterion(category, criterion_id)
        ChampionshipLoader().delete_championship_criterion(
            championship_uniq_id, category_id, criterion_id
        )
        championship = self._load_championship(championship_uniq_id)
        return self._render_criteria_modal(
            request,
            championship,
            self._stored_category(championship, category_id),
        )
