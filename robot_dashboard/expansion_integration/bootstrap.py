"""Small app hook: OFF imports no expansion services and creates no workers."""
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse
from .flags import ExpansionFlags


def configure_expansion(app, environ, *, review_inputs=None):
    flags = ExpansionFlags.from_environ(environ)
    if flags.enabled:
        from .host import install_expansion
        from .review_owner import configured_owner
        owner = configured_owner(app, flags, environ, review_inputs)
        install_expansion(app, flags, owner)

    def index_response(*, headers):
        if flags.enabled:
            from .host import dashboard_index
            return HTMLResponse(dashboard_index(flags), headers=headers)
        return FileResponse(Path(__file__).resolve().parents[1] / "static/index.html",
                            headers=headers)

    return index_response
