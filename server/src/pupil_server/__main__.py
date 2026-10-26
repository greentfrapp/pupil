"""Serve Pupil: `python -m pupil_server --client client/dist`, as `pnpm start` does.

One process for the API and the built client, without the dev server's reloading. The host
and port come from the settings (PUPIL_HOST, PUPIL_PORT).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from pupil_server.app import create_app
from pupil_server.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="pupil_server", description="Serve Pupil.")
    parser.add_argument(
        "--client", type=Path, help="the built client to serve, e.g. client/dist; API only without"
    )
    args = parser.parse_args()
    client_dir = args.client.resolve() if args.client else None
    if client_dir is not None and not (client_dir / "index.html").is_file():
        parser.error(f"no built client in {client_dir}; build it with `pnpm --filter client build`")

    app = create_app(settings, client_dir=client_dir)
    print(f"Pupil is at http://{settings.host}:{settings.port}", flush=True)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        loop="pupil_server.loop:loop_factory",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
