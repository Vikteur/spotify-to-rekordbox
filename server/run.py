"""Start the local server.

Port 8000 is popular — Docker dashboards, other dev servers, admin panels all
squat on it. If one is already there, uvicorn's own failure is easy to miss in
a scrolling terminal and the browser cheerfully shows you *that* app instead.
So: check the port first and say plainly what to do.

Set PORT to use a different one:  PORT=8010 npm run dev
"""

import os
import socket
import sys

import uvicorn

HOST = "127.0.0.1"  # local only: the server can read your filesystem
DEFAULT_PORT = 8000


def port_is_taken(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


def main() -> int:
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    if port_is_taken(HOST, port):
        print(
            f"\nPort {port} is already in use by another program, so this app "
            f"cannot start there.\n"
            f"Whatever you see at http://{HOST}:{port} right now is that other "
            f"program, not this one\n(the DJ app has no sign-in, so a login "
            f"page there is not us — only /g/<token> guest links are gated).\n\n"
            f"Either stop it, or run on a different port:\n"
            f"    PORT={port + 10} npm run dev      # macOS / Linux\n"
            f"    $env:PORT={port + 10}; npm run dev  # Windows PowerShell\n\n"
            f"To see what is holding the port:\n"
            f"    lsof -i :{port}                  # macOS / Linux\n"
            f"    netstat -ano | findstr :{port}   # Windows\n",
            file=sys.stderr,
        )
        return 1

    uvicorn.run(
        "server.main:app", host=HOST, port=port, reload="--reload" in sys.argv
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
