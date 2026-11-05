"""Small app hook: OFF imports no expansion services and creates no workers."""
from fastapi.responses import HTMLResponse
from .flags import ExpansionFlags


def configure_expansion(app, environ, *, review_inputs=None):
    flags = ExpansionFlags.from_environ(environ)
    if flags.enabled:
        from .host import install_expansion
        from .review_owner import configured_owner
        owner = configured_owner(app, flags, environ, review_inputs)
        install_expansion(app, flags, owner)
    else:
        from .host import install_landing
        install_landing(app, flags)

    def index_response(*, headers):
        from .host import dashboard_index
        return HTMLResponse(dashboard_index(flags), headers=headers)

    return index_response
