"""Declarative spec describing what parts of an event should be loaded
from SQLite.

The default spec loads everything (matches pre-existing behaviour). Hot
paths can opt into loading less by attaching a `@needs_event(...)`
decorator to the route handler; `WebContext.get_event` reads that
metadata at request time and passes a tighter spec to the loader.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from litestar.plugins.htmx import HTMXRequest


@dataclass
class EventLoadSpec:
    """What to load from the event database.

    Defaults match the old `load_stored_event` behaviour (everything).
    Hot paths can flip flags off to skip queries / Python construction.
    """

    # Top-level event tables.
    load_players: bool = True
    load_tournaments: bool = True
    load_timers: bool = True
    load_screens: bool = True
    load_families: bool = True
    load_rotators: bool = True
    load_display_controllers: bool = True
    load_accounts: bool = True

    # When set, only this tournament is loaded (the others are skipped
    # entirely). Useful for endpoints that target one tournament.
    selected_tournament_id: int | None = None

    # Per-tournament sub-loaders (apply to whichever tournaments are
    # loaded — selected one or all of them).
    tournament_load_tie_breaks: bool = True
    tournament_load_prize_groups: bool = True
    tournament_load_players: bool = True
    tournament_load_boards: bool = True


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

# Attribute name used to stash the spec factory on a route handler.
_SPEC_FACTORY_ATTR = '__event_load_spec_factory__'

# Optional integer-valued path parameters that can be plugged into the spec.
SpecFactory = Callable[['HTMXRequest', dict[str, Any]], EventLoadSpec]


def needs_event(
    *,
    load_players: bool = True,
    load_tournaments: bool = True,
    load_timers: bool = True,
    load_screens: bool = True,
    load_families: bool = True,
    load_rotators: bool = True,
    load_display_controllers: bool = True,
    load_accounts: bool = True,
    selected_tournament_param: str | None = None,
    tournament_load_tie_breaks: bool = True,
    tournament_load_prize_groups: bool = True,
    tournament_load_players: bool = True,
    tournament_load_boards: bool = True,
):
    """Attach an event-load spec factory to a route handler.

    The factory is invoked at request time to build an `EventLoadSpec`
    that may depend on path parameters (e.g. `selected_tournament_param`
    pulls the value of a path/query/body parameter and stores it as
    `selected_tournament_id`).

    The handler signature is left untouched so Litestar's parameter
    injection still works.
    """

    def factory(request: 'HTMXRequest', params: dict[str, Any]) -> EventLoadSpec:
        selected_id: int | None = None
        if selected_tournament_param is not None:
            raw = params.get(selected_tournament_param)
            if raw is not None:
                try:
                    selected_id = int(raw)
                except (TypeError, ValueError):
                    selected_id = None
        return EventLoadSpec(
            load_players=load_players,
            load_tournaments=load_tournaments,
            load_timers=load_timers,
            load_screens=load_screens,
            load_families=load_families,
            load_rotators=load_rotators,
            load_display_controllers=load_display_controllers,
            load_accounts=load_accounts,
            selected_tournament_id=selected_id,
            tournament_load_tie_breaks=tournament_load_tie_breaks,
            tournament_load_prize_groups=tournament_load_prize_groups,
            tournament_load_players=tournament_load_players,
            tournament_load_boards=tournament_load_boards,
        )

    def decorator(handler):
        setattr(handler, _SPEC_FACTORY_ATTR, factory)
        return handler

    return decorator


def get_handler_spec(
    handler: Any, request: 'HTMXRequest', params: dict[str, Any]
) -> EventLoadSpec | None:
    """Return the spec attached to a handler via `@needs_event`, or None."""
    factory: SpecFactory | None = getattr(handler, _SPEC_FACTORY_ATTR, None)
    if factory is None:
        return None
    return factory(request, params)
