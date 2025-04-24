from litestar.plugins.htmx import HTMXRequest

from plugins.ffe.util import PlayerFFELicence


class FFESessionHandler:
    ADMIN_PLAYERS_FILTER_LEAGUES_KEY: str = 'admin_players_filter_leagues'

    @classmethod
    def set_session_admin_players_filter_leagues(
        cls, request: HTMXRequest, leagues: list[str]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_LEAGUES_KEY] = leagues

    @classmethod
    def get_session_admin_players_filter_leagues(
        cls, request: HTMXRequest
    ) -> list[str]:
        return [
            d for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_LEAGUES_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_LICENCES_KEY: str = 'admin_players_filter_licences'

    @classmethod
    def set_session_admin_players_filter_licences(
        cls, request: HTMXRequest, licences: list[PlayerFFELicence]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_LICENCES_KEY] = licences

    @classmethod
    def get_session_admin_players_filter_licences(
        cls, request: HTMXRequest
    ) -> list[PlayerFFELicence]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, PlayerFFELicence) else PlayerFFELicence(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_LICENCES_KEY, [])
        ]
