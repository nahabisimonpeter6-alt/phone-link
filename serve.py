#!/usr/bin/env python3
"""Run PhoneLink with the production Waitress WSGI server behind HTTPS."""
import argparse
import os

from wsgi import create_application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    try:
        from waitress import serve
    except ImportError:
        parser.error("Install hosting dependencies: python -m pip install -r requirements-deploy.txt")
    try:
        app = create_application()
    except ValueError as error:
        parser.error(str(error))
    settings = dict(host=args.host, port=args.port, threads=8, connection_limit=100,
                    max_request_body_size=8192, max_request_header_size=16384,
                    channel_timeout=30, expose_tracebacks=False)
    # Trust forwarded client IPs only when an explicitly configured reverse proxy
    # strips client-supplied headers. Never trust arbitrary X-Forwarded-For values.
    if os.environ.get("PHONELINK_TRUSTED_PROXY"):
        settings.update(trusted_proxy=os.environ["PHONELINK_TRUSTED_PROXY"],
                        trusted_proxy_headers={"x-forwarded-for"}, trusted_proxy_count=1)
    serve(app, **settings)


if __name__ == "__main__":
    main()
