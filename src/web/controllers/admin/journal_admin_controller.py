import csv
from functools import cached_property
import hashlib
import io
import json
from typing import Annotated, Any

from litestar import delete, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body, FromPath, FromQuery
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Response, Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data import journal
from data.access_levels.actions import AuthAction
from data.journal import (
    JournalAction,
    JournalCategory,
    JournalEntry,
    Author,
    AuthorKind,
    Source,
    SourceKind,
    author_label,
    identity_key,
    load_journal,
    load_journal_entry,
    load_journal_filter_options,
    parse_identity_key,
    source_label,
)
from database.sqlite.event.event_database import EventDatabase
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message

#: How many entries the page shows at first, and adds each time it is
#: scrolled to its end: an event of several days holds thousands.
PAGE_SIZE = 100


class JournalAdminWebContext(BaseEventAdminWebContext):
    """The journal is read here only, and only the part the page shows: the
    entries matching the filters, a page at a time, and what the filters
    offer when the whole page is drawn."""

    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        category: str | None = None,
        author: str | None = None,
        source: str | None = None,
    ):
        super().__init__(request)
        self.tournament_id = tournament_id
        try:
            self.category = JournalCategory(category) if category else None
        except ValueError:
            self.category = None
        self.author_key = author or None
        self.source_key = source or None

    def author_label(self, author: Author | None) -> str:
        """Who acted: a staff account by the name it has, or, once deleted, by
        the one the entry of its deletion gives, saying it is deleted."""
        if author is None or author.kind != AuthorKind.ACCOUNT:
            return author_label(author)
        account = self.get_admin_event().accounts_by_id.get(author.account_id or 0)
        if account is not None:
            return author_label(author, account.full_name)
        deleted_name = self.deleted_account_names.get(author.account_id or 0)
        return _('{account} (deleted account)').format(account=deleted_name or '?')

    @cached_property
    def deleted_account_names(self) -> dict[int, str]:
        with EventDatabase(self.get_admin_event().uniq_id) as database:
            return database.load_journal_deleted_account_names()

    def tournament_label(self, entry: JournalEntry) -> str | None:
        if entry.tournament_id is None:
            return None
        tournament = self.get_admin_event().tournaments_by_id.get(entry.tournament_id)
        return tournament.name if tournament else entry.tournament_name

    def entries_context(
        self, after_id: int | None = None, before_id: int | None = None
    ) -> dict[str, Any]:
        """A page of entries: the most recent ones, those written before the
        entry *before_id* (the page scrolled to its end), or those written
        after the entry *after_id* (the page kept up to date). One more is
        read to know whether there are older ones to load."""
        entries = load_journal(
            self.get_admin_event().uniq_id,
            tournament_id=self.tournament_id,
            category=self.category,
            author=parse_identity_key(self.author_key),
            source=parse_identity_key(self.source_key),
            limit=PAGE_SIZE + 1,
            after_id=after_id,
            before_id=before_id,
        )
        return {
            'admin_event_tab': 'admin-event-journal-tab',
            'journal_entries': entries[:PAGE_SIZE],
            'journal_more': after_id is None and len(entries) > PAGE_SIZE,
            'journal_tournament_label': self.tournament_label,
            'journal_author_label': self.author_label,
            'journal_source_label': source_label,
        }

    def tab_context(self) -> dict[str, Any]:
        return self.entries_context() | self.filters_context()

    def filters_context(self) -> dict[str, Any]:
        """What the filters offer, read from the journal, with a key that
        tells the page whether what it offers is still up to date."""
        event = self.get_admin_event()
        options = load_journal_filter_options(event.uniq_id)
        tournament_names = {
            tournament_id: (
                tournament.name
                if (tournament := event.tournaments_by_id.get(tournament_id))
                else name or '?'
            )
            for tournament_id, name in options.tournament_names.items()
        }
        author_labels = {
            identity_key((kind, account_id, None)): (
                self.author_label(
                    Author(
                        AuthorKind(kind),
                        account_id if isinstance(account_id, int) else None,
                    )
                )
                if kind is not None and kind in AuthorKind._value2member_map_
                else _('Nobody')
            )
            for kind, account_id, _name in options.authors
        }
        source_labels = {
            identity_key((kind, name, host)): (
                # The devices of the network all read as another device: the
                # filter tells them apart by their address.
                _('{source} ({address})').format(
                    source=source_label(source), address=host
                )
                if host is not None
                else source_label(source)
            )
            for kind, name, host in options.sources
            for source in [
                Source(
                    SourceKind(kind)
                    if kind is not None and kind in SourceKind._value2member_map_
                    else SourceKind.APPLICATION,
                    name if isinstance(name, str) else None,
                    host,
                )
            ]
        }
        tournament_options = {'': _('All the tournaments')} | {
            str(tournament_id): name
            for tournament_id, name in sorted(
                tournament_names.items(), key=lambda item: item[1]
            )
        }
        category_options = {'': _('Everything')} | {
            category.value: category.label for category in options.categories
        }
        author_options = {'': _('Everyone')} | dict(
            sorted(author_labels.items(), key=lambda item: item[1])
        )
        source_options = {'': _('Everywhere')} | dict(
            sorted(source_labels.items(), key=lambda item: item[1])
        )
        options_key = hashlib.sha1(
            json.dumps(
                [tournament_options, category_options, author_options, source_options]
            ).encode()
        ).hexdigest()[:16]
        return {
            'journal_has_entries': options.has_entries,
            'journal_filters': {
                'tournament_id': str(self.tournament_id or ''),
                'category': self.category.value if self.category else '',
                'author': self.author_key or '',
                'source': self.source_key or '',
            },
            'journal_tournament_options': tournament_options,
            'journal_category_options': category_options,
            'journal_author_options': author_options,
            'journal_source_options': source_options,
            'journal_options_key': options_key,
        }


class JournalAdminController(BaseEventAdminController):
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.VIEW_JOURNAL),
    ]

    @classmethod
    def _render(
        cls,
        web_context: JournalAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        """The page, or the modal of *template_context*, which reads nothing
        of the journal."""
        if template_context and 'modal' in template_context:
            return cls._admin_base_event_render(
                web_context.template_context
                | {'admin_event_tab': 'admin-event-journal-tab'}
                | template_context
            )
        return cls._admin_base_event_render(
            web_context.template_context | web_context.tab_context()
        )

    @get(
        path='/event/{event_uniq_id:str}/journal',
        name='admin-event-journal-tab',
    )
    async def htmx_admin_event_journal_tab(
        self,
        request: HTMXRequest,
        tournament_id: FromQuery[str | None] = None,
        category: FromQuery[str | None] = None,
        author: FromQuery[str | None] = None,
        source: FromQuery[str | None] = None,
    ) -> Template:
        return self._render(
            JournalAdminWebContext(
                request,
                int(tournament_id)
                if tournament_id and tournament_id.isdigit()
                else None,
                category,
                author,
                source,
            )
        )

    @get(
        path='/event/{event_uniq_id:str}/journal/entries',
        name='admin-event-journal-entries',
    )
    async def htmx_admin_event_journal_entries(
        self,
        request: HTMXRequest,
        tournament_id: FromQuery[str | None] = None,
        category: FromQuery[str | None] = None,
        author: FromQuery[str | None] = None,
        source: FromQuery[str | None] = None,
        after_id: FromQuery[int | None] = None,
        before_id: FromQuery[int | None] = None,
        options_key: FromQuery[str | None] = None,
    ) -> Template:
        """The entries alone, for the filters; with *after_id*, the entries
        written since that one, which the page adds on top of those it shows;
        with *before_id*, the next page of older ones, which it adds below."""
        web_context = JournalAdminWebContext(
            request,
            int(tournament_id) if tournament_id and tournament_id.isdigit() else None,
            category,
            author,
            source,
        )
        if before_id:
            return Template(
                template_name='admin/journal/rows.html',
                context=web_context.template_context
                | web_context.entries_context(before_id=before_id),
            )
        # The page keeping up to date tells which options its filters show:
        # it is told to draw them again when the journal holds others.
        filters_stale = (
            options_key is not None
            and web_context.filters_context()['journal_options_key'] != options_key
        )
        trigger_event = 'journal-filters-stale' if filters_stale else None
        if after_id:
            return HTMXTemplate(
                template_name='admin/journal/rows.html',
                context=web_context.template_context
                | web_context.entries_context(after_id),
                re_target='#journal-rows',
                re_swap='afterbegin',
                trigger_event=trigger_event,
                after='settle',
            )
        # A page showing no entry has no rows to add to: it is drawn again.
        return HTMXTemplate(
            template_name='admin/journal/entries.html',
            context=web_context.template_context | web_context.entries_context(),
            trigger_event=trigger_event,
            after='settle',
        )

    @get(
        path='/event/{event_uniq_id:str}/journal/filters',
        name='admin-event-journal-filters',
    )
    async def htmx_admin_event_journal_filters(
        self,
        request: HTMXRequest,
        tournament_id: FromQuery[str | None] = None,
        category: FromQuery[str | None] = None,
        author: FromQuery[str | None] = None,
        source: FromQuery[str | None] = None,
    ) -> Template:
        """The filters, with the options the journal holds now and the
        choices made kept."""
        web_context = JournalAdminWebContext(
            request,
            int(tournament_id) if tournament_id and tournament_id.isdigit() else None,
            category,
            author,
            source,
        )
        return Template(
            template_name='admin/journal/filters.html',
            context=web_context.template_context | web_context.filters_context(),
        )

    # -------------------------------------------------------------------------
    # Notes
    # -------------------------------------------------------------------------

    @classmethod
    def _note_modal_context(
        cls,
        web_context: JournalAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        return {
            'modal': 'journal-note',
            'data': data or {},
            'errors': errors or {},
            'journal_note_tournament_options': {'': _('None in particular')}
            | {
                str(tournament.id): tournament.name
                for tournament in event.sorted_tournaments
            },
        }

    @get(
        path='/event/{event_uniq_id:str}/journal/note-modal',
        name='admin-journal-note-modal',
    )
    async def htmx_admin_journal_note_modal(self, request: HTMXRequest) -> Template:
        web_context = JournalAdminWebContext(request)
        return self._render(web_context, self._note_modal_context(web_context))

    @post(
        path='/event/{event_uniq_id:str}/journal/note',
        name='admin-journal-note-create',
    )
    async def htmx_admin_journal_note_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = JournalAdminWebContext(request)
        event = web_context.get_admin_event()
        text = WebContext.form_data_to_str(data, 'text')
        errors: dict[str, str] = {}
        if not text:
            errors['text'] = _('Please write the note.')
        tournament = None
        try:
            tournament_id = WebContext.form_data_to_int(data, 'tournament_id')
        except ValueError:
            tournament_id = -1
        if tournament_id is not None:
            tournament = event.tournaments_by_id.get(tournament_id)
            if tournament is None:
                errors['tournament_id'] = _('Invalid value.')
        round_ = None
        if tournament is not None and tournament.current_round:
            round_ = tournament.current_round
        if errors:
            return self._render(
                web_context, self._note_modal_context(web_context, data, errors)
            )
        journal.record(
            event.uniq_id,
            JournalAction.NOTE,
            tournament=tournament,
            round_=round_,
            text=text,
        )
        Message.success(request, _('The note has been added to the journal.'))
        return self._render(JournalAdminWebContext(request))

    @delete(
        path='/event/{event_uniq_id:str}/journal/note/{entry_id:int}',
        name='admin-journal-note-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_journal_note_delete(
        self,
        request: HTMXRequest,
        entry_id: FromPath[int],
    ) -> Template:
        web_context = JournalAdminWebContext(request)
        entry = load_journal_entry(web_context.get_admin_event().uniq_id, entry_id)
        if entry is None or not entry.is_note:
            raise NotFoundException(f'Note [{entry_id}] not found.')
        with EventDatabase(web_context.get_admin_event().uniq_id, True) as database:
            database.delete_stored_journal_entry(entry_id)
        Message.success(request, _('The note has been deleted.'))
        return self._render(JournalAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Download
    # -------------------------------------------------------------------------

    @get(
        path='/event/{event_uniq_id:str}/journal.csv',
        name='admin-journal-download',
    )
    async def admin_journal_download(self, request: HTMXRequest) -> Response[str]:
        web_context = JournalAdminWebContext(request)
        event = web_context.get_admin_event()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                _('Date'),
                _('Tournament'),
                _('Round'),
                _('Category'),
                _('Action'),
                _('Note'),
                _('Who'),
                _('Where'),
                _('Address'),
            ]
        )
        for entry in reversed(load_journal(event.uniq_id)):
            writer.writerow(
                [
                    entry.at.isoformat(sep=' ', timespec='seconds'),
                    web_context.tournament_label(entry) or '',
                    entry.round or '',
                    entry.category.label if entry.category else '',
                    entry.sentence,
                    entry.text or '',
                    web_context.author_label(entry.author),
                    source_label(entry.source),
                    entry.host or '',
                ]
            )
        return Response(
            # The BOM lets spreadsheets read the file as UTF-8.
            content='﻿' + output.getvalue(),
            media_type='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': (
                    f'attachment; filename="{event.uniq_id}-journal.csv"'
                )
            },
        )
