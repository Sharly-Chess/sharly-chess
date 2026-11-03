from litestar import get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Template

from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)


class ComponentGalleryAdminController(BaseAdminController):
    """Every administration component, in each of its variants, on one page:
    where the components are reviewed, in both themes, and where their
    contrast is tested. Served only when running from the sources."""

    @get(path='/dev/components', name='admin-component-gallery')
    async def htmx_admin_component_gallery(self, request: HTMXRequest) -> Template:
        return HTMXTemplate(
            template_name='admin/components/gallery/page.html',
            context=AdminWebContext(request).template_context,
        )
