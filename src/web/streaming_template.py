"""
Opt-in streaming template responses.

Provides StreamingHTMXTemplate, a drop-in replacement for HTMXTemplate
that renders templates in chunks via a thread pool and streams the result,
preventing server blocking on large templates.
"""

import asyncio
from typing import Any

from common.i18n import get_locale, set_locale
from litestar.plugins.htmx import HTMXTemplate
from litestar.response import Stream


class StreamingHTMXTemplate(HTMXTemplate):
    """HTMXTemplate subclass that streams the rendered template response."""

    def to_asgi_response(
        self,
        app: Any,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        async def stream_template():
            current_locale = get_locale()

            def render_in_thread():
                set_locale(current_locale)

                template_engine = request.app.template_engine
                jinja_env = template_engine.engine
                template = jinja_env.get_template(self.template_name)

                context = self.context or {}
                if 'request' not in context:
                    context = {'request': request, **context}

                return list(template.generate(**context))

            chunks = await asyncio.to_thread(render_in_thread)

            for chunk in chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0)

        stream_response = Stream(stream_template(), media_type='text/html')
        stream_response.headers.update(self.headers)

        return stream_response.to_asgi_response(app=app, request=request, **kwargs)
