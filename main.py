"""Run the local FEAT-001 application."""

from argparse import ArgumentParser
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from aip import create_app


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    """Keep one browser connection from blocking other local clients."""

    daemon_threads = True


def main() -> None:
    parser = ArgumentParser(description="Run AIP Manual Sprint Capture")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--database", default="data/aip.sqlite3")
    args = parser.parse_args()
    app = create_app(args.database)
    with make_server(args.host, args.port, app, server_class=ThreadedWSGIServer) as server:
        print("AIP is running at:")
        print(f"  http://127.0.0.1:{args.port}")
        print(f"  http://192.168.0.30:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
