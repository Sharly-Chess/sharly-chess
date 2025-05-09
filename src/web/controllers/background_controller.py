import validators
from litestar import get
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import MediaType

from common.background import inline_image_url
from web.controllers.base_controller import WebContext, BaseController


class BackgroundWebContext(WebContext):
    def __init__(
        self,
        request: HTMXRequest,
        color: str,
        image: str,
    ):
        super().__init__(request)
        self.background: dict[str, str] = {
            'color': color,
        }
        if not image:
            self.background['url'] = ''
        elif validators.url(image) or image.startswith('/'):
            self.background['url'] = f'url({image})'
        # elif image.startswith('/'):
        #     self.background['url'] = f'url({image})'
        else:
            self.background['url'] = f'url({inline_image_url(image)})'


class BackgroundController(BaseController):
    """
    The /background URL is called with an image and a color parameter.
    The JSON response contains a color and a url parameter where url is generated from the image (inline data when a
    file in /custom is sent).
    """

    @get(path='/background', name='background', media_type=MediaType.JSON)
    async def background(
        self,
        request: HTMXRequest,
        color: str,
        image: str,
    ) -> dict[str, str]:
        return BackgroundWebContext(request, color=color, image=image).background
