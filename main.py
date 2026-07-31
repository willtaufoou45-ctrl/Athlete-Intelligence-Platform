"""Run the local FEAT-001 application."""

from argparse import ArgumentParser
from wsgiref.simple_server import make_server

from aip import create_app


def main() -> None:
    parser = ArgumentParser(description="Run AIP Manual Sprint Capture")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--database", default="data/aip.sqlite3")
    args = parser.parse_args()
    app = create_app(args.database)
    with make_server(args.host, args.port, app) as server:
        print(f"AIP is running at http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
