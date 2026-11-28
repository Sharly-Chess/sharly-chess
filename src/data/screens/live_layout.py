"""The live update of the layout of the screens.

While the live update of a screen is on, the layout set in its edit modal or
with the controls shown on the screen itself, and the alert message set in
the modal, are shown at once by every device that shows the screen, without
being stored: the values are kept here, in memory, until they are saved (from
the modal or from the controls), the live update is turned off, or the modal
is closed without saving.

The live update of a multi-screen is that of its family, whose pages all
follow it. The live updates are kept under the key of their screen or family
(see `live_key`).
"""

from typing import Any

LAYOUT_FIELDS: tuple[str, ...] = (
    'columns',
    'font_size',
    'timer_id',
    'background_image',
    'background_color',
    'background_blurred',
    'message_default',
    'message_text',
)
"""The fields that the live update shows: those of the layout, and the alert
message."""

_live_layouts: dict[tuple[str, str], dict[str, Any]] = {}


def live_key(kind: str, uniq_id: str) -> str:
    """The key of the live update of a screen (*kind* ``'screen'``) or of a
    family (``'family'``), whose uniq IDs could be the same."""
    return f'{kind}:{uniq_id}'


def live_layout(event_uniq_id: str, target_key: str) -> dict[str, Any] | None:
    """The layout values of the screen or family of key *target_key* of the event
    *event_uniq_id* while its live update is on, ``None`` otherwise."""
    return _live_layouts.get((event_uniq_id, target_key))


def live_value(event_uniq_id: str, target_key: str, field: str, default: Any) -> Any:
    """The live value of *field* for the screen or family of key *target_key*, or
    *default* when its live update is off or does not set *field*."""
    values = _live_layouts.get((event_uniq_id, target_key))
    if values is None or field not in values:
        return default
    return values[field]


def start_live_layout(
    event_uniq_id: str, target_key: str, values: dict[str, Any]
) -> None:
    """Turns on the live update of the screen or family of key *target_key* with
    the layout *values* (those shown by its edit modal)."""
    _live_layouts[(event_uniq_id, target_key)] = dict(values)


def update_live_layout(
    event_uniq_id: str, target_key: str, values: dict[str, Any]
) -> bool:
    """Changes the layout values of a live update. Returns whether a value
    changed; nothing changes when the live update is off."""
    current = _live_layouts.get((event_uniq_id, target_key))
    if current is None:
        return False
    changed = any(current.get(field) != value for field, value in values.items())
    current.update(values)
    return changed


def stop_live_layout(event_uniq_id: str, target_key: str) -> dict[str, Any] | None:
    """Turns off the live update of the screen or family of key *target_key*, and
    returns the values it showed (``None`` if it was off)."""
    return _live_layouts.pop((event_uniq_id, target_key), None)


def stop_event_live_layouts(event_uniq_id: str) -> None:
    """Turns off the live updates of the screens of an event (when the event
    is deleted or reloaded from its database)."""
    for key in [key for key in _live_layouts if key[0] == event_uniq_id]:
        del _live_layouts[key]
