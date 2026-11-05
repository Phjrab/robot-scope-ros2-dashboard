"""Short-lived grants for one explicitly shared, non-driving review workspace.

An operator provisions a private database offline. A one-time code becomes one
opaque browser session atomically. Only SHA-256 digests of random secrets persist.
"""
import argparse
from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time


SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
MAX_TTL = 3600


class AccessUnavailable(Exception):
    """The private credential store is missing, unsafe or unavailable."""


def _digest(value):
    return hashlib.sha256(value.encode("ascii")).digest()


def _private_path(database, *, existing=True):
    path = Path(database)
    if not path.is_absolute() or path.resolve() != path:
        raise AccessUnavailable("canonical absolute database path required")
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise AccessUnavailable("owner-only private directory required")
    if existing:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise AccessUnavailable("owner-only regular database required")
    return path


class ReviewAccess:
    def __init__(self, database, *, clock=time.time):
        self.database = database
        self.clock = clock

    def _connect(self):
        # The serving application must never implicitly create a credential store.
        path = _private_path(self.database)
        return sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=1)

    def initialize(self):
        path = _private_path(self.database, existing=False)
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE grants (
                id TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('read','review')),
                expires INTEGER NOT NULL, code BLOB UNIQUE, session BLOB UNIQUE
            )""")

    def issue(self, role, ttl):
        if role not in {"read", "review"} or type(ttl) is not int or not 1 <= ttl <= MAX_TTL:
            raise ValueError("read/review role and 1–3600 second lifetime required")
        code, grant = secrets.token_urlsafe(32), secrets.token_hex(12)
        now = int(self.clock())
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM grants WHERE expires <= ?", (now,))
            if db.execute("SELECT count(*) FROM grants").fetchone()[0] >= 256:
                raise AccessUnavailable("active grant limit reached")
            db.execute("INSERT INTO grants VALUES (?, ?, ?, ?, NULL)",
                       (grant, role, now + ttl, _digest(code)))
        return grant, code

    def redeem(self, code):
        if not isinstance(code, str) or not SECRET.fullmatch(code):
            return None
        session = secrets.token_urlsafe(32)
        with closing(self._connect()) as db, db:
            changed = db.execute("UPDATE grants SET code=NULL, session=? WHERE code=? AND expires>?",
                                 (_digest(session), _digest(code), int(self.clock())))
            if not changed.rowcount:
                return None
        return session

    def lookup(self, session):
        if not isinstance(session, str) or not SECRET.fullmatch(session):
            return None
        now = int(self.clock())
        with closing(self._connect()) as db:
            row = db.execute("SELECT role, expires FROM grants WHERE session=? AND expires>?",
                             (_digest(session), now)).fetchone()
        if row:
            return {"role": row[0], "remaining_seconds": row[1] - now}
        return None

    def logout(self, session):
        if isinstance(session, str) and SECRET.fullmatch(session):
            with closing(self._connect()) as db, db:
                db.execute("DELETE FROM grants WHERE session=?", (_digest(session),))

    def revoke(self, grant):
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM grants WHERE id=?", (grant,)).rowcount


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("init")
    issue = commands.add_parser("issue")
    issue.add_argument("role", choices=["read", "review"])
    issue.add_argument("--ttl", type=int, default=900)
    commands.add_parser("revoke").add_argument("grant")
    args = parser.parse_args()
    store = ReviewAccess(args.database)
    if args.action == "init":
        store.initialize()
    elif args.action == "issue":
        grant, code = store.issue(args.role, args.ttl)
        print(f"Revocation ID: {grant}\nOne-time review code: {code}")
    elif not store.revoke(args.grant):
        parser.exit(1, "Grant unavailable\n")


if __name__ == "__main__":
    main()
