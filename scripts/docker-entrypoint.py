"""Wait for existing dependencies, then hand process ownership to the service."""
import os
import socket
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg


def database_url(url, host):
    if not host:
        return url
    parts = urlsplit(url)
    credentials = parts.netloc.rsplit("@", 1)[0] + "@" if "@" in parts.netloc else ""
    return urlunsplit(parts._replace(netloc=f"{credentials}{host}:{parts.port or 5432}"))


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "web"
    if role not in ("web", "worker"):
        raise SystemExit("Expected web or worker")
    url = database_url(os.environ["WATCH_SIEVE_DATABASE_URL"], os.getenv("WATCH_SIEVE_DATABASE_HOST"))
    os.environ["WATCH_SIEVE_DATABASE_URL"] = url
    deadline = time.monotonic() + 120
    while True:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            if role == "worker":
                with socket.create_connection((os.environ["SNAIL_SERVER_HOST"], int(os.environ["SNAIL_SERVER_PORT"])), timeout=3):
                    pass
            break
        except (psycopg.Error, OSError):
            # Do not log connection strings or credentials.
            if time.monotonic() >= deadline:
                raise SystemExit("Dependency readiness timed out; container restart policy will retry")
            print(f"{role}: waiting for dependencies", flush=True)
            time.sleep(3)
    command = "watch-sieve-web" if role == "web" else "watch-sieve-snailjob"
    os.execvp(command, [command])


if __name__ == "__main__":
    main()
