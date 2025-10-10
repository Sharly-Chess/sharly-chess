from litestar.plugins.htmx import HTMXRequest


def index_url(request: HTMXRequest) -> str:
    return request.app.route_reverse('index')


def admin_event_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse('admin-event', event_uniq_id=event_uniq_id)


def admin_event_players_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse(
        'admin-event-players-tab', event_uniq_id=event_uniq_id
    )


def admin_event_tournaments_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse(
        'admin-event-tournaments-tab', event_uniq_id=event_uniq_id
    )


def admin_event_pairings_url(
    request: HTMXRequest,
    event_uniq_id: str,
    tournament_id: int,
) -> str:
    return request.app.route_reverse(
        'admin-event-pairings-tab',
        event_uniq_id=event_uniq_id,
        tournament_id=tournament_id,
    )


def admin_upload_item_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse(
        'admin-event-upload-item', event_uniq_id=event_uniq_id
    )
