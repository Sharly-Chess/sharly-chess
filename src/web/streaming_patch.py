"""
Monkey-patch to make ALL Template responses use streaming automatically.

This patches Litestar's Template class to always stream template rendering,
preventing server blocking on large templates.
"""

import asyncio
from typing import Any

from litestar.plugins.htmx import HTMXTemplate
from litestar.response import Template, Stream


# Store original to_asgi_response methods
_original_template_to_asgi = Template.to_asgi_response
_original_htmx_template_to_asgi = HTMXTemplate.to_asgi_response


def _streaming_to_asgi_response(
    self: Template,
    app: Any,
    request: Any,
    **kwargs: Any,
) -> Any:
    """
    Replacement for Template.to_asgi_response that always streams.

    This method renders templates in chunks in a thread pool and streams
    the result to prevent blocking the server.

    Accepts all kwargs that Litestar passes (background, cookies, headers, etc.)
    """

    async def stream_template():
        # Render template chunks in thread pool
        def render_in_thread():
            template_engine = request.app.template_engine
            jinja_env = template_engine.engine
            template = jinja_env.get_template(self.template_name)

            # Prepare context with request and other variables Litestar adds
            context = self.context or {}
            # Add request to context if not already present
            if 'request' not in context:
                context = {'request': request, **context}

            # Generate chunks instead of full render
            return list(template.generate(**context))

        # Render chunks in thread pool
        chunks = await asyncio.to_thread(render_in_thread)

        # Stream chunks to client, yielding control between each
        for chunk in chunks:
            yield chunk.encode('utf-8')
            await asyncio.sleep(0)  # Yield control to event loop

    # Create streaming response
    stream_response = Stream(stream_template(), media_type='text/html')

    # For HTMXTemplate, copy all headers that were set during __init__
    # HTMXTemplate sets HTMX headers (HX-Retarget, HX-Trigger, etc.) in its __init__ method
    if isinstance(self, HTMXTemplate):
        # Copy all headers from the template to the stream response
        stream_response.headers.update(self.headers)

    # Convert Stream to ASGI response, passing through all kwargs
    # Note: This must be synchronous, so we return the ASGI app directly
    return stream_response.to_asgi_response(app=app, request=request, **kwargs)


def apply_streaming_patch() -> None:
    # Patch both Template and HTMXTemplate classes
    Template.to_asgi_response = _streaming_to_asgi_response  # type: ignore
    HTMXTemplate.to_asgi_response = _streaming_to_asgi_response  # type: ignore


def remove_streaming_patch() -> None:
    Template.to_asgi_response = _original_template_to_asgi  # type: ignore
    HTMXTemplate.to_asgi_response = _original_htmx_template_to_asgi  # type: ignore
