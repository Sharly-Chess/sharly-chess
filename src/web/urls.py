from litestar.contrib.htmx.request import HTMXRequest


def index_url(request: HTMXRequest) -> str:
    return request.app.route_reverse('index')

def admin_url(
    request: HTMXRequest,
) -> str:
    return request.app.route_reverse('admin')

def admin_event_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse('admin-event', event_uniq_id=event_uniq_id)

def admin_event_config_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse('admin-event-config-tab', event_uniq_id=event_uniq_id)

def admin_event_players_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse('admin-event-players-tab', event_uniq_id=event_uniq_id)

def admin_event_tournaments_url(
    request: HTMXRequest,
    event_uniq_id: str,
) -> str:
    return request.app.route_reverse('admin-event-tournaments-tab', event_uniq_id=event_uniq_id)
