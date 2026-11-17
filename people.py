"""Who may see what: people, their signed-in devices, and links.

data/people.json holds
  people    {id: {name, created}}            "owner" is the person at this PC and always exists (rename in the app: "שיתוף")
  sessions  {sha256(cookie): {person, device, created, seen}}
  links     {sha256(token): {kind, by, created, expires, used, ...}}
            kind "invite": joins a NEW person to one profile (search)       -> profile
            kind "attach": signs another device in as an EXISTING person    -> person
            kind "ad":     shows one ad, read-only, to whoever has the link -> profile, ad

Cookies and link tokens are random and only their hashes are stored, so reading this file does not let anyone in.
The app speaks plain HTTP: fine inside a home network or a Tailscale network, not on the open internet.
"""
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

FILE = Path(__file__).resolve().parent / "data" / "people.json"
LOCK = threading.RLock()
OWNER = "owner"
SESSION_DAYS, LIFE = 90, {"invite": timedelta(days=7), "attach": timedelta(minutes=15), "ad": timedelta(days=30)}
ONE_USE = {"invite", "attach"}
_fails = {}  # ip -> times of wrong tokens: guessing gets slow, then refused


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def load():
    try:
        db = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        db = {}
    db.setdefault("people", {}).setdefault(OWNER, {"name": "אני", "created": _now()})
    db.setdefault("sessions", {})
    db.setdefault("links", {})
    return db


def save(db):
    FILE.parent.mkdir(exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def names():
    return {pid: p["name"] for pid, p in load()["people"].items()}


def last_seen():
    out = {}
    for s in load()["sessions"].values():
        out[s["person"]] = max(out.get(s["person"], ""), s.get("seen") or "")
    return out


def add_person(name):
    name = " ".join(str(name or "").split())[:30]
    if not name:
        raise ValueError("name")
    with LOCK:
        db = load()
        pid = "u" + secrets.token_hex(4)
        db["people"][pid] = {"name": name, "created": _now()}
        save(db)
    return pid


def rename(person, name):
    name = " ".join(str(name or "").split())[:30]
    if not name:
        raise ValueError("name")
    with LOCK:
        db = load()
        db["people"][person]["name"] = name
        save(db)


def new_session(person, device):
    sid = secrets.token_urlsafe(32)
    with LOCK:
        db = load()
        db["sessions"][_hash(sid)] = {"person": person, "device": str(device or "")[:80], "created": _now(), "seen": _now()}
        save(db)
    return sid


def person_of_session(sid):
    with LOCK:
        db = load()
        s = db["sessions"].get(_hash(sid))
        if not s or s["person"] not in db["people"]:
            return None
        if datetime.fromisoformat(s["created"]) < datetime.now() - timedelta(days=SESSION_DAYS):
            del db["sessions"][_hash(sid)]
            save(db)
            return None
        if s.get("seen", "")[:15] != _now()[:15]:  # note "seen" once in ten minutes, not on every request
            s["seen"] = _now()
            save(db)
        return s["person"]


def end_sessions(person):
    with LOCK:
        db = load()
        db["sessions"] = {k: s for k, s in db["sessions"].items() if s["person"] != person}
        save(db)


def new_link(kind, by, **data):
    token = secrets.token_urlsafe(18)
    with LOCK:
        db = load()
        now = datetime.now()
        db["links"] = {k: v for k, v in db["links"].items() if v["expires"] > now.isoformat()}  # drop the expired
        db["links"][_hash(token)] = dict(data, kind=kind, by=by, created=_now(), used=None,
                                         expires=(now + LIFE[kind]).isoformat(timespec="seconds"))
        save(db)
    return token


def peek(token):
    """The link's record if it is still good, else None."""
    rec = load()["links"].get(_hash(str(token)))
    if not rec or rec["expires"] < _now() or (rec["kind"] in ONE_USE and rec.get("used")):
        return None
    return rec


def use(token):
    with LOCK:
        db = load()
        rec = db["links"].get(_hash(token))
        if rec and rec["kind"] in ONE_USE:
            rec["used"] = _now()
            save(db)


def slow_down(ip):
    """True when this address tried too many wrong links lately (10 in ten minutes)."""
    recent = [t for t in _fails.get(ip, []) if t > time.time() - 600]
    _fails[ip] = recent
    return len(recent) >= 10


def wrong(ip):
    _fails.setdefault(ip, []).append(time.time())
    time.sleep(0.4)
