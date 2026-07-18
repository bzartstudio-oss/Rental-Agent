"""Production WSGI entry point — see docs/45_Deployment_Guide.md
"Production Startup".

`app` is what any real WSGI server (waitress, gunicorn) imports; running this
module directly serves it with waitress, using the same `WebConfiguration`
every other entry point (`flask run`, tests) already resolves from the
environment, so a container and a local `flask run` never disagree about
host/port/debug/secret key.
"""

from __future__ import annotations

from src.web.application import create_app
from src.web.configuration import WebConfiguration

app = create_app()

if __name__ == "__main__":
    from waitress import serve

    configuration = WebConfiguration.from_env()
    serve(app, host=configuration.host, port=configuration.port)
