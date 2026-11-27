from collections.abc import Collection, Iterable

# The fields each screen keeps for itself, never written by a multiple edit.
PER_ITEM_FIELDS: frozenset[str] = frozenset(
    {
        'name',
        'uniq_id',
        'menu_text',
        'tournament_id',
        'first',
        'last',
        'init_set_tournament_ids',
        'background_image',
        'background_image_upload',
        'background_color',
        'background_color_checkbox',
        'background_blurred',
    }
)

FAMILY_ID_PREFIX = 'family-'


def parse_item_ids(item_ids: Iterable[str]) -> tuple[list[int], list[int]]:
    """The screen ids and the paged-screen ids of the collection item ids
    *item_ids* (``12`` for a screen, ``family-5`` for a paged screen).
    Raises ``ValueError`` on an id of neither form."""
    screen_ids: list[int] = []
    family_ids: list[int] = []
    for item_id in dict.fromkeys(item_ids):
        if item_id.startswith(FAMILY_ID_PREFIX):
            family_ids.append(int(item_id.removeprefix(FAMILY_ID_PREFIX)))
        else:
            screen_ids.append(int(item_id))
    return screen_ids, family_ids


def _comparable(value: str | None) -> str:
    # An unticked switch reads 'off' or is missing, depending on its source.
    return '' if value in (None, 'off') else value


def shared_form_data(
    items_form_data: list[dict[str, str]],
) -> tuple[dict[str, str], set[str]]:
    """The form values that all of *items_form_data* hold alike, and the
    fields whose values differ from one item to another."""
    shared: dict[str, str] = {}
    mixed: set[str] = set()
    fields: dict[str, None] = {}
    for form_data in items_form_data:
        fields.update(dict.fromkeys(form_data))
    for field in fields:
        if field in PER_ITEM_FIELDS:
            continue
        values = {_comparable(form_data.get(field)) for form_data in items_form_data}
        if len(values) == 1:
            shared[field] = values.pop()
        else:
            mixed.add(field)
    return shared, mixed


def merged_form_data(
    item_form_data: dict[str, str],
    submitted_data: dict[str, str],
    changed_fields: Collection[str],
) -> dict[str, str]:
    """The form values of one item once the fields *changed_fields* of the
    multiple-edit form *submitted_data* are applied to them. A changed field
    absent from the form (an unticked switch, a disabled field) is removed."""
    merged = dict(item_form_data)
    for field in changed_fields:
        if field in PER_ITEM_FIELDS:
            continue
        if field in submitted_data:
            merged[field] = submitted_data[field]
        else:
            merged.pop(field, None)
    return merged
