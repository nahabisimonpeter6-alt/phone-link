"""Production WSGI entry point. The hosting platform handles HTTP and TLS.

Set PHONELINK_PUBLIC_URL and PHONELINK_DB before importing/serving application.
The local development server continues to work without these settings.
"""
from email.message import Message
from http import HTTPStatus
from io import BytesIO
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

from server import AppState, Handler, ROOT


class WSGIRequest(Handler):
    """Adapt the existing request handlers to a hosting provider's WSGI server."""

    def __init__(self, state, environ):
        self.server = state
        self.client_address = (environ.get("REMOTE_ADDR", "unknown"), 0)
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                self.headers[key[5:].replace("_", "-")] = str(value)
        for key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            if environ.get(key):
                self.headers[key.replace("_", "-")] = str(environ[key])
        if not self.headers.get("Host"):
            self.headers["Host"] = environ.get("SERVER_NAME", "localhost")
        self.path = environ.get("PATH_INFO", "/")
        if environ.get("QUERY_STRING"):
            self.path += "?" + environ["QUERY_STRING"]
        self.rfile = environ["wsgi.input"]
        self.wfile = BytesIO()
        self.response_headers = []
        self.status = "500 Internal Server Error"

    def send_response(self, code, message=None):
        self.status = f"{code} {message or HTTPStatus(code).phrase}"

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass


def create_application(db_path=None, public_url=None):
    url = public_url or os.environ.get("PHONELINK_PUBLIC_URL", "")
    if urlsplit(url).scheme != "https":
        raise ValueError("Set PHONELINK_PUBLIC_URL to your public HTTPS address before deploying.")
    database = Path(db_path or os.environ.get("PHONELINK_DB", str(ROOT / "data/phonelink.sqlite3")))
    state = AppState(database, url)

    def app(environ, start_response):
        request = WSGIRequest(state, environ)
        method = environ.get("REQUEST_METHOD", "GET")
        if method not in ("GET", "POST", "DELETE", "HEAD"):
            request.respond(405, {"error": "Method not allowed."})
            request.response_headers.append(("Allow", "GET, HEAD, POST, DELETE"))
        else:
            request.dispatch("GET" if method == "HEAD" else method)
        start_response(request.status, request.response_headers)
        return [b"" if method == "HEAD" else request.wfile.getvalue()]

    return app


class LazyApplication:
    """WSGI hosts can set environment variables before the first request."""
    def __init__(self):
        self.app = None
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        if self.app is None:
            with self.lock:
                if self.app is None:
                    self.app = create_application()
        return self.app(environ, start_response)


application = LazyApplication()
