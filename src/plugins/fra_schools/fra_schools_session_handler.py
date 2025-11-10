from litestar.plugins.htmx import HTMXRequest


class FRASchoolsSessionHandler:
    FILTER_SCHOOLS_KEY: str = 'fra_schools_filtered_schools_schools'

    @classmethod
    def set_session_filter_schools(cls, request: HTMXRequest, schools: list[int]):
        request.session[cls.FILTER_SCHOOLS_KEY] = schools

    @classmethod
    def get_session_filter_schools(cls, request: HTMXRequest) -> list[int]:
        return request.session.get(cls.FILTER_SCHOOLS_KEY, [])
