"""Apartment boards in one place: several boards, one data shape, one profile per person.

    python app.py                      the app at http://127.0.0.1:7461
    python app.py serve --lan          the same, also for devices you invited on the home network
    python app.py sync <profile> [board]   pull the profile's search now (the app must be running, open in Chrome)
    python app.py list <profile>       the ads that fit, best first
    python app.py set <profile> <ad id> [--status S] [--note "..."] [--summary "..."]

Each profile is one file, data/profiles/<id>.json: the person's preferences and every ad pulled for them, in our own
shape (boards.py), each with its own change log. Boards are read in the user's own Chrome through the small
extension in extension/ (its collectors/*.js read the board's page). Nothing is sent to a board and no owner is
contacted.
"""
import argparse
import ipaddress
import json
import math
import queue
import re
import secrets
import socket
import statistics
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import boards
import people

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "data" / "profiles"
STORES = ROOT / "data" / "cities"  # shared mode: one store of ads per city and deal, read once for everybody
MAPS_KEY_FILE = ROOT / "data" / "maps-key.txt"  # optional: your own Google Maps Embed key, for Street View in the app
try:
    import local_settings as LOCAL  # an optional file next to app.py, for one computer only; not part of the package
except ImportError:
    LOCAL = None
if getattr(LOCAL, "MAPS_KEY_FILE", None):
    MAPS_KEY_FILE = Path(LOCAL.MAPS_KEY_FILE)
PORT = 7461
# Pull a little over the budget: the market comparison needs the ads just above it. Less for a purchase, where a
# search already returns far more ads than one pull reads.
MARGIN = {"rent": 1.25, "sale": 1.1}
STATUSES = ["", "shortlist", "contacted", "visit", "rejected"]
TRACKED = ["price", "description", "rooms", "sqm", "floor", "seller", "entrance"]
YAD2_FEATURES = list(boards.YAD2_MAP_FEATURES)
LOCK = threading.RLock()
GEO_LOCK = threading.Lock()
CITIES = {c["name"]: c for c in json.loads((ROOT / "cities.json").read_text(encoding="utf-8"))}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# ---------------- profiles on disk ----------------

def profile_path(pid):
    if not re.fullmatch(r"[a-z0-9-]{1,40}", pid):
        raise KeyError("no such profile")
    return (STORES if re.fullmatch(STORE_ID, pid) else PROFILES) / f"{pid}.json"


def load_profile(pid):
    path = profile_path(pid)
    if not path.exists():
        raise KeyError("no such profile")
    p = json.loads(path.read_text(encoding="utf-8"))
    p["prefs"].setdefault("deal", "rent")  # profiles from before the app could search for a purchase
    if p.get("store"):
        # A search over a shared city store: the ads are the city's, and only this search's own marks and summaries
        # are kept with it. Everything that reads a profile sees one whole profile.
        spath, mine = profile_path(p["store"]), p.get("mine") or {}
        s = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {"ads": {}, "meta": {}}
        p["ads"] = {i: dict(r, **mine.get(i, {})) for i, r in s["ads"].items()}
        p["ads"].update(p.pop("own", None) or {})  # ads this person pasted in: theirs, not the city's
        p["meta"] = dict(p["meta"], last_sync=s["meta"].get("last_sync"), syncs=s["meta"].get("syncs") or [])
    return p


def save_profile(p):
    path = profile_path(p["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if p.get("store"):  # the city's ads are not this search's to write: only its own marks go to disk
        p = dict(p, mine={i: {k: r[k] for k in ("marks", "summary") if r.get(k)} for i, r in p["ads"].items()
                          if r["board"] in boards.BOARDS and (r.get("marks") or r.get("summary"))},
                 own={i: r for i, r in p["ads"].items() if r["board"] not in boards.BOARDS},
                 ads={}, meta={k: v for k, v in p["meta"].items() if k not in ("last_sync", "syncs")})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def list_profiles(person=people.OWNER):
    """The profiles this person may see: all of them for the owner, the ones they were invited to for anyone else."""
    out = []
    for path in sorted(PROFILES.glob("*.json")):
        p = load_profile(path.stem)
        if person != people.OWNER and person not in p.get("members", []):
            continue
        vs = build_views(p, person)
        out.append({"id": p["id"], "name": p["name"], "prefs": p["prefs"], "last_sync": p["meta"].get("last_sync"),
                    "fits": sum(1 for v in vs if v["fit"] == "yes" and not v["gone_since"]),
                    "total": sum(1 for v in vs if not v["gone_since"]),
                    "favorites": sum(1 for v in vs if v["fav_by"]), "members": len(p.get("members", []))})
    return out


def clean_prefs(raw):
    """Only what the questionnaire asks, with the types we rely on."""
    num = lambda v: float(v) if v not in (None, "") else None
    if raw.get("city") not in CITIES:
        raise ValueError("city")
    hoods = {h["name"] for h in CITIES[raw["city"]]["hoods"]}
    return {
        "who": str(raw.get("who") or "")[:200],
        "deal": boards.deal_of(raw),
        "city": raw["city"],
        "hoods": [h for h in raw.get("hoods") or [] if h in hoods],
        "radius_km": min(max(num(raw.get("radius_km")) or 1.2, 0.3), 10),
        "price_max": num(raw.get("price_max")), "price_min": num(raw.get("price_min")),
        "rooms_min": num(raw.get("rooms_min")), "rooms_max": num(raw.get("rooms_max")),
        "sqm_min": num(raw.get("sqm_min")),
        "private_only": bool(raw.get("private_only")),
        "access": {"need": bool((raw.get("access") or {}).get("need")),
                   "max_floor": int((raw.get("access") or {}).get("max_floor") or 0)},
        "features": {k: v for k, v in (raw.get("features") or {}).items() if k in boards.FEATURES and v in ("must", "nice")},
        "hide": [h for h in raw.get("hide") or [] if h in ("roommates", "religious", "basement")],
    }


# ---------------- shared mode: one store per city, read in turn ----------------
# For a hosted service: nobody pulls for themselves. Each city (and deal) is read once, with a wide search and
# without full ads, into a store that every search of that city looks through; cities wait in one line.
STORE_ID = r"c\d{4}-(rent|sale)"
SHARED = False          # `serve --shared`: a new search is a view over its city's store
FRESH_HOURS = 12        # a store younger than this is not read again
CITY_GAP = 45           # seconds of rest between two cities
QUEUE = []              # store ids waiting to be read, in order
QUEUE_INFO = {"times": [], "last": None}  # how long the last pulls took (seconds), for the waiting estimate


def store_of(prefs):
    return f"c{CITIES[prefs['city']]['code']}-{boards.deal_of(prefs)}"


def ensure_store(prefs):
    sid = store_of(prefs)
    with LOCK:
        if not profile_path(sid).exists():
            wide = {"deal": boards.deal_of(prefs), "city": prefs["city"], "hoods": [], "radius_km": 1.2, "price_max": None,
                    "price_min": None, "rooms_min": None, "rooms_max": None, "sqm_min": None, "private_only": False,
                    "access": {"need": False, "max_floor": 0}, "features": {}, "hide": [], "who": "", "lists_only": True}
            save_profile({"id": sid, "name": prefs["city"], "created": now_iso(), "prefs": wide, "meta": {"syncs": []}, "ads": {}})
    return sid


def store_age_hours(sid):
    try:
        at = parse_time(load_profile(sid)["meta"].get("last_sync"))
    except KeyError:
        return None
    return None if not at else (datetime.now() - at).total_seconds() / 3600


def enqueue(sid):
    """Ask for a city to be read. Answers its place in the line (1 = next or being read), or 0 when it is fresh."""
    age = store_age_hours(sid)
    with LOCK:
        if SYNC["running"] and SYNC["profile"] == sid:
            return 1
        if sid in QUEUE:
            return QUEUE.index(sid) + 1 + (1 if SYNC["running"] else 0)
        if age is not None and age < FRESH_HOURS:
            return 0
        QUEUE.append(sid)
        return len(QUEUE) + (1 if SYNC["running"] else 0)


def queue_state(sid=None):
    """What a person waiting for a city sees: where it stands and about how long that is."""
    times = QUEUE_INFO["times"][-6:]
    each = (sum(times) / len(times) if times else 240) + CITY_GAP
    with LOCK:
        reading = SYNC["profile"] if SYNC["running"] and re.fullmatch(STORE_ID, SYNC["profile"] or "") else None
        line = ([reading] if reading else []) + list(QUEUE)
    pos = line.index(sid) + 1 if sid in line else 0
    return {"line": len(line), "pos": pos, "wait_min": math.ceil(pos * each / 60) if pos else 0, "reading": reading,
            "last": QUEUE_INFO["last"]}


def queue_worker():
    """One city at a time, in the order asked, with a rest between cities. Runs for as long as the app does."""
    while True:
        time.sleep(2)
        with LOCK:
            sid = QUEUE[0] if QUEUE and not SYNC["running"] else None
        if not sid:
            continue
        if not browser_ready() and not hasattr(LOCAL, "browser"):
            time.sleep(10)  # no browser is connected to read with: the line waits
            continue
        t0 = time.time()
        if not start_sync(sid):
            continue
        with LOCK:
            if sid in QUEUE:
                QUEUE.remove(sid)
        while SYNC["running"]:
            time.sleep(1)
        QUEUE_INFO["times"].append(time.time() - t0)
        QUEUE_INFO["last"] = {"store": sid, "at": now_iso(), "seconds": round(time.time() - t0), "error": SYNC["error"]}
        time.sleep(CITY_GAP)


def create_profile(name, raw_prefs):
    name = str(name or "").strip()[:40]
    if not name:
        raise ValueError("name")
    prefs = clean_prefs(raw_prefs)
    with LOCK:
        n = len(list(PROFILES.glob("*.json"))) + 1 if PROFILES.exists() else 1
        pid = f"p{n}"
        while profile_path(pid).exists():
            n += 1
            pid = f"p{n}"
        p = {"id": pid, "name": name, "created": now_iso(), "prefs": prefs, "meta": {"syncs": []}, "ads": {}}
        if SHARED:
            p["store"] = ensure_store(prefs)
        save_profile(p)
    return p


# ---------------- one ad through time ----------------

def merge_ad(p, norm, now, from_detail=False):
    """Fold a board's fresh answer into the stored ad and log what changed. Returns "new", "changed" or None."""
    rec = p["ads"].get(norm["id"])
    if rec and not from_detail and rec.get("detail_at") and len(norm.get("images") or []) < len(rec.get("images") or []):
        norm.pop("images", None)  # a list row carries one thumbnail; the full ad already gave all the photos
    if rec is None:
        rec = {"first_seen": now, "status": "", "note": "", "summary": "", "changes": [], "features": [],
               "features_known": False, "gone_since": None}
        p["ads"][norm["id"]] = rec
        result = "new"
    else:
        result = None
        for field in TRACKED:
            new, old = norm.get(field), rec.get(field)
            if field in norm and new is not None and old is not None and new != old:
                rec["changes"].append({"at": now, "field": field, "from": old, "to": new})
                result = "changed"
        if not from_detail and norm.get("images") is not None and len(norm["images"]) != len(rec.get("images") or []):
            rec["changes"].append({"at": now, "field": "images", "from": len(rec.get("images") or []), "to": len(norm["images"])})
        if rec.get("gone_since"):
            rec["changes"].append({"at": now, "field": "back", "from": rec["gone_since"], "to": None})
            rec["gone_since"] = None
            result = "changed"
    feats = norm.pop("features", None)
    if feats is not None:
        # A full ad replaces the list; a list item (yad2's map tags) only adds, so it cannot wipe what the full ad said.
        rec["features"] = feats if from_detail or not rec.get("detail_at") else sorted(set(rec["features"]) | set(feats))
    for k, v in norm.items():
        if v is not None or k not in rec:
            rec[k] = v
    if from_detail:
        rec["detail_at"] = now
    else:
        rec["last_seen"] = now
    return result


def mark_gone(p, board, seen, now):
    gone = 0
    for ad_id, rec in p["ads"].items():
        if rec.get("board") == board and ad_id not in seen and not rec.get("gone_since"):
            rec["gone_since"] = now
            rec["changes"].append({"at": now, "field": "gone", "from": None, "to": None})
            gone += 1
    return gone


# ---------------- what an ad means for this profile ----------------

def km_between(a, b):
    if not (a.get("lat") and a.get("lon") and b.get("lat") and b.get("lon")):
        return None
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def feats_of(ad):
    f = set(ad.get("features") or [])
    if ad.get("condition_renovated"):
        f.add("renovated")
    return f


def fit_of(ad, prefs, text):
    """("yes" | "maybe" | "no", why not, what is not known, what to ask about)."""
    no, unknown, warn = [], [], []
    feats, known, floor = feats_of(ad), ad.get("features_known"), ad.get("floor")
    if ad.get("type") in boards.NOT_A_HOME:
        return "no", ["לא דירה: " + boards.TYPES[ad["type"]]], [], []
    price = ad.get("price")
    if price is None:
        unknown.append("אין מחיר במודעה")
    elif prefs.get("price_max") and price > prefs["price_max"]:
        no.append(f"מעל התקציב ב-{int(price - prefs['price_max']):,} ₪")
    elif prefs.get("price_min") and price < prefs["price_min"]:
        no.append("מתחת למחיר המינימלי")
    rooms = ad.get("rooms")
    if rooms is not None and ((prefs.get("rooms_min") and rooms < prefs["rooms_min"]) or (prefs.get("rooms_max") and rooms > prefs["rooms_max"])):
        no.append(f"{rooms:g} חדרים")
    if prefs.get("sqm_min") and ad.get("sqm") and ad["sqm"] < prefs["sqm_min"]:
        no.append(f"{ad['sqm']} מ\"ר בלבד")
    if prefs.get("private_only") and ad.get("seller") != "private":
        (unknown if ad.get("seller") is None else no).append("לא ידוע אם תיווך" if ad.get("seller") is None else "תיווך")
    if prefs["access"]["need"]:
        if "elevator" in feats or (floor is not None and floor <= prefs["access"]["max_floor"]):
            if "stairs" in text["flags"]:
                warn.append(f"הבעלים מזכיר מדרגות (\"{text.get('stairs_text')}\")")
            if "basement" in text["flags"]:
                warn.append("מרתף: לברר כמה מדרגות יורדים")
            if floor and floor >= 1 and "elevator" not in feats and ad.get("on_pillars"):
                warn.append("בניין על עמודים: קומה 1 היא שתי קומות מדרגות")
        elif floor is None:
            unknown.append("לא צוינה קומה")
        elif not (known or ad.get("elevator_known")):
            unknown.append(f"קומה {floor}, לא ידוע אם יש מעלית")
        else:
            no.append(f"קומה {floor} בלי מעלית")
    for f, level in prefs.get("features", {}).items():
        if level == "must" and f not in feats:
            (no if known else unknown).append(("אין " if known else "לא ידוע אם יש ") + boards.FEATURES[f])
    hide_he = {"roommates": "מודעת שותפים", "religious": "מיועד לשומרי שבת / דתיים", "basement": "מרתף"}
    for flag in prefs.get("hide", []):
        if flag in text["flags"]:
            no.append(hide_he[flag])
    if boards.deal_of(prefs) == "sale" and "key_money" in text["flags"]:
        no.append("דמי מפתח: לא בעלות על הדירה")
    return ("no" if no else "maybe" if unknown else "yes"), no, unknown, warn


def area_of(ad, prefs, centers):
    if not centers:
        return "in", None
    dists = [d for d in (km_between(ad, c) for c in centers) if d is not None]
    dist = min(dists) if dists else None
    if ad.get("hood") in prefs["hoods"] or (dist is not None and dist <= 0.45):
        return "in", dist
    if dist is None:
        return "unknown", None
    return ("near" if dist <= prefs["radius_km"] else "out"), dist


def _key(text):
    return re.sub(r"\W+", "", text or "")[:40]


def _words(street):
    words = {w for w in re.split(r"[\s'\"׳״.-]+", street or "") if len(w) >= 4}
    return words or ({_key(street)} if _key(street) else set())  # "אחד העם", "ברץ": a name of short words counts whole


def same_flat(a, b):
    """Two ads from different boards that are one flat: same rooms, price within 5%, similar size, same place."""
    if a.get("rooms") != b.get("rooms") or not a.get("price") or not b.get("price"):
        return False
    if abs(a["price"] - b["price"]) > 0.05 * b["price"]:
        return False
    if a.get("sqm") and b.get("sqm") and abs(a["sqm"] - b["sqm"]) > 0.2 * b["sqm"]:
        return False
    same_text = _key(a.get("description")) and _key(a.get("description")) == _key(b.get("description"))
    same_street = _words(a.get("street")) & _words(b.get("street"))
    same_house = a.get("house_no") and str(a.get("house_no")) == str(b.get("house_no"))
    exact = a["price"] == b["price"] and a.get("sqm") and a.get("sqm") == b.get("sqm")
    same_floor = a.get("floor") is not None and a.get("floor") == b.get("floor")
    if same_street and same_floor and a["price"] == b["price"] and not (a.get("house_no") and b.get("house_no")):
        return True
    if "hood" in (a.get("loc_approx"), b.get("loc_approx")):  # no real pin on one side: the address has to match
        return bool(same_street and same_house)
    d = km_between(a, b)
    if same_street and same_house:  # the same written address: the pins may sit far apart (yad2 shifts its pins)
        return d is None or d <= 3
    if d is None or d > 0.4:
        return False
    if d <= 0.08 and not (a.get("loc_approx") or b.get("loc_approx")):
        return True
    # Boards pin the same address up to a few hundred metres apart (and Komo gives no pin at all): ask for more proof.
    return bool(same_text or (same_street and (exact or same_house) and d <= 0.3))


def find_duplicates(ads):
    """{secondary ad id: primary ad id} for flats that appear on more than one board. The private owner's ad leads;
    between equals, the board that comes first in boards.BOARDS (it has the richer record)."""
    roots, dup = [], {}
    for board in list(boards.BOARDS) + list(boards.OTHER):
        for a in (x for x in ads if x["board"] == board):
            m = next((r for r in roots if r["board"] != board and same_flat(a, r)), None)
            if m is None:
                roots.append(a)
            elif a.get("seller") == "private" and m.get("seller") != "private":
                for k, v in list(dup.items()):
                    if v == m["id"]:
                        dup[k] = a["id"]
                dup[m["id"]] = a["id"]
                roots[roots.index(m)] = a
            else:
                dup[a["id"]] = m["id"]
    return dup


def market_of(ad, pool, deal="rent"):
    """Price against similar flats nearby (all boards): similar rooms and size, within 2 km. Needs 6 to speak.
    Rent compares the monthly price. A purchase compares the price per square metre (flats for sale differ far
    more in size), with one room more or less; an ad without a size falls back to the whole price."""
    if not ad.get("price") or ad.get("rooms") is None:
        return None
    per_sqm = deal == "sale" and bool(ad.get("sqm"))
    mine = ad["price"] / ad["sqm"] if per_sqm else ad["price"]
    comps = []
    for o in pool:
        if o["id"] == ad["id"] or abs((o.get("rooms") or 99) - ad["rooms"]) > (1 if per_sqm else 0.5):
            continue
        if per_sqm and not o.get("sqm"):
            continue
        if ad.get("sqm") and o.get("sqm") and not 0.7 <= o["sqm"] / ad["sqm"] <= 1.4:
            continue
        d = km_between(ad, o)
        if d is not None and d > 2:
            continue
        comps.append((d, o["price"] / o["sqm"] if per_sqm else o["price"]))
    # A price per metre belongs to a neighbourhood: when there are enough flats within 1 km, only they count.
    near = [c for c in comps if c[0] is not None and c[0] <= 1]
    km = 1 if per_sqm and len(near) >= 8 else 2
    values = [v for _, v in (near if km == 1 else comps)]
    if len(values) < 6:
        return None
    med = statistics.median(values)
    return {"median": round(med), "n": len(values), "delta_pct": round((mine - med) / med * 100),
            "per": "sqm" if per_sqm else "flat", "km": km}


def cost_of(ad, text, deal="rent"):
    if not ad.get("price"):
        return None
    if deal == "sale":  # the price is paid once; the bills are what living there costs every month
        monthly = [[k, v] for k, v in (["ועד בית", ad.get("vaad")], ["ארנונה", ad.get("arnona")]) if v]
        return {"parts": [["מחיר מבוקש", ad["price"]]], "total": ad["price"], "included": [], "excluded": [],
                "per_sqm": round(ad["price"] / ad["sqm"]) if ad.get("sqm") else None,
                "monthly": monthly, "monthly_total": sum(v for _, v in monthly)}
    parts = [["שכירות", ad["price"]]]
    if ad.get("vaad") and "vaad" not in text["included"]:
        parts.append(["ועד בית", ad["vaad"]])
    if ad.get("arnona") and "arnona" not in text["included"]:
        parts.append(["ארנונה", ad["arnona"]])
    return {"parts": parts, "total": sum(v for _, v in parts),
            "included": [boards.BILLS_HE[k] for k in text["included"]],
            "excluded": [boards.BILLS_HE[k] for k in text["excluded"]]}


# ---------------- places around (OpenStreetMap) ----------------

PLACES = ROOT / "data" / "places"
KINDS = {"supermarket": "סופר", "pharmacy": "בית מרקחת", "clinic": "מרפאה", "rail": "רכבת / רכבת קלה", "park": "פארק",
         "synagogue": "בית כנסת"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
WALK_LIMIT = {"supermarket": 6, "pharmacy": 8, "clinic": 10, "rail": 8}  # minutes that still count as "next door"


def load_places(city):
    try:
        return json.loads((PLACES / f"{city.get('code')}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def fetch_places(city):
    """Everyday places of one city from OpenStreetMap's public Overpass service, saved in data/places/. Only the
    city's bounding box is sent."""
    import urllib.parse
    import urllib.request
    pts = city["hoods"] or ([city] if city.get("lat") else [])
    if not pts:
        return []
    s, n = min(p["lat"] for p in pts) - 0.012, max(p["lat"] for p in pts) + 0.012
    w, e = min(p["lon"] for p in pts) - 0.014, max(p["lon"] for p in pts) + 0.014
    box = f"({s:.4f},{w:.4f},{n:.4f},{e:.4f})"
    query = ("[out:json][timeout:50];(" + "".join(f"nwr{sel}{box};" for sel in (
        '["shop"="supermarket"]', '["amenity"="pharmacy"]', '["amenity"~"^(clinic|doctors)$"]', '["healthcare"="clinic"]',
        '["railway"~"^(tram_stop|station|halt)$"]', '["leisure"="park"]["name"]',
        '["amenity"="place_of_worship"]["religion"="jewish"]')) + ");out center tags;")
    elements, last = None, None
    for host in OVERPASS:  # the public servers are often busy: try the next one
        req = urllib.request.Request(host, data=urllib.parse.urlencode({"data": query}).encode(),
                                     headers={"User-Agent": "apartment-board/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                elements = json.loads(r.read())["elements"]
            break
        except (OSError, ValueError, KeyError) as e:
            last = e
    if elements is None:
        raise OSError(str(last))
    out, seen = [], set()
    for el in elements:
        t = el.get("tags") or {}
        lat, lon = el.get("lat") or (el.get("center") or {}).get("lat"), el.get("lon") or (el.get("center") or {}).get("lon")
        kind = ("supermarket" if t.get("shop") == "supermarket" else "pharmacy" if t.get("amenity") == "pharmacy"
                else "clinic" if t.get("amenity") in ("clinic", "doctors") or t.get("healthcare") == "clinic"
                else "rail" if t.get("railway") in ("tram_stop", "station", "halt") else "park" if t.get("leisure") == "park"
                else "synagogue" if t.get("amenity") == "place_of_worship" else None)
        if not kind or not lat:
            continue
        name = t.get("name:he") or t.get("name") or KINDS[kind]
        key = (kind, name, round(lat, 3), round(lon, 3))  # the two platforms of one stop are one place
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "name": name, "lat": round(lat, 6), "lon": round(lon, 6)})
    PLACES.mkdir(parents=True, exist_ok=True)
    (PLACES / f"{city['code']}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def near_of(ad, by_kind):
    """The nearest place of each kind. Minutes are an estimate: straight line x 1.3, at an easy 4.5 km/h."""
    if not ad.get("lat"):
        return {}
    out = {}
    for kind, places in by_kind.items():
        best = min(places, key=lambda p: (p["lat"] - ad["lat"]) ** 2 + ((p["lon"] - ad["lon"]) * 0.85) ** 2, default=None)
        if best:
            m = km_between(ad, best) * 1000
            out[kind] = {"name": best["name"], "m": round(m), "min": max(1, math.ceil(m * 1.3 / 75)), "lat": best["lat"], "lon": best["lon"]}
    return out


def haggle_of(ad, now, deal="rent"):
    why = []
    listed = parse_time(ad.get("listed_at"))
    if listed and (now - listed).days >= (60 if deal == "sale" else 30):  # a flat for sale stays up longer
        why.append(f"{(now - listed).days} ימים באוויר")
    drops = sum(1 for e in ad.get("board_events") or [] if e.get("kind") in ("priceDrop", "before"))
    drops += sum(1 for c in ad.get("changes") or [] if c["field"] == "price" and c["to"] < c["from"])
    if drops:
        why.append("המחיר כבר ירד" + (f" {drops} פעמים" if drops > 1 else ""))
    return why


def score_of(v, prefs, ad):
    s, why = 55, []
    sale = boards.deal_of(prefs) == "sale"
    similar = "מחיר למ\"ר בדירות דומות" if (v["market"] or {}).get("per") == "sqm" else "דירות דומות"

    def add(points, text):
        nonlocal s
        s += points
        why.append([points, text])

    if prefs["hoods"]:
        if v["area"] == "in":
            add(15, "בשכונה שביקשת")
        elif v["area"] == "near":
            add(8, f"{v['dist_km']:.1f} ק\"מ מהשכונה")
        else:
            add(-5, "רחוק מהשכונה")
    feats = set(v["features"])
    nice = [boards.FEATURES[f] for f, lvl in prefs.get("features", {}).items() if lvl == "nice" and f in feats]
    if nice:
        add(min(16, 4 * len(nice)), "יש " + ", ".join(nice))
    m = v["market"]
    if m and "odd_price" in v["flags"]:
        add(-6, f"מחיר חריג, {-m['delta_pct']}% מתחת לדומות: לברר מה בדיוק מוצע")
    elif m:
        d = m["delta_pct"]
        if d <= -10:
            add(10, f"{-d}% מתחת ל{similar}")
        elif d <= -3:
            add(5, f"{-d}% מתחת ל{similar}")
        elif d > 10:
            add(-8, f"{d}% מעל {similar}")
        elif d >= 3:
            add(-4, f"{d}% מעל {similar}")
    if prefs["access"]["need"]:
        if "accessible" in feats:
            add(6, "מסומנת נגישה")
        if "elevator" in feats or (ad.get("floor") is not None and ad["floor"] <= 0):
            add(4, "בלי מדרגות לפי המודעה")
        if v["warn"]:
            add(-8, "יש מה לברר על מדרגות")
    close = [KINDS[k] for k, lim in WALK_LIMIT.items() if v["near"].get(k) and v["near"][k]["min"] <= lim]
    if close:
        add(min(8, 2 * len(close)), "ממש ליד: " + ", ".join(close))
    n_img = len(v["images"])
    if n_img == 0:
        add(-6, "בלי תמונות")
    elif n_img >= 5:
        add(2, "הרבה תמונות")
    if not v.get("description"):
        add(-4, "בלי תיאור")
    if v["days_listed"] is not None:
        if v["days_listed"] <= 3:
            add(3, "מודעה טרייה")
        elif v["days_listed"] > (120 if sale else 60):
            add(-3, "מפורסמת מעל " + ("ארבעה חודשים" if sale else "חודשיים"))
    if v["fit"] == "maybe":
        add(-6, "חסר מידע במודעה")
    why.sort(key=lambda w: -abs(w[0]))
    return max(1, min(99, s)), why


def build_views(p, me=people.OWNER):
    """Every stored ad with all that is worked out from it for this profile. Nothing here is saved."""
    prefs, now = p["prefs"], datetime.now()
    deal = boards.deal_of(prefs)
    who = people.names()
    city = CITIES.get(prefs["city"], {})
    centers = [h for h in city.get("hoods", []) if h["name"] in prefs["hoods"]]
    ads = list(p["ads"].values())
    texts = {a["id"]: boards.read_text(a) for a in ads}
    live = [a for a in ads if not a.get("gone_since")]
    dup = find_duplicates(live)
    by_id = {a["id"]: a for a in ads}
    pool = [a for a in live if a["id"] not in dup and a.get("price") and a.get("type") not in boards.NOT_A_HOME
            and "roommates" not in texts[a["id"]]["flags"] and "key_money" not in texts[a["id"]]["flags"]]
    with_insights = [a for a in live if a.get("insights")]
    widened, last_url = set(), {}  # (board, sync time) of every pull whose search differed from the one before it
    for s in p["meta"].get("syncs") or []:
        for b in s.get("boards") or []:
            if "error" in b or "skipped" in b:
                continue
            if b["board"] not in last_url or b.get("url") != last_url[b["board"]]:
                widened.add((b["board"], s["at"]))
            last_url[b["board"]] = b.get("url")
    recent_from = now - timedelta(days=3)
    by_kind = {}
    for pl in load_places(city) or []:
        by_kind.setdefault(pl["kind"], []).append(pl)
    out = []
    for ad in ads:
        if ad["id"] in dup:
            continue
        text = texts[ad["id"]]
        twins = [by_id[s] for s, prim in dup.items() if prim == ad["id"]]
        merged = dict(ad)
        for t in twins:  # what the other board knows and this one does not
            merged["features"] = sorted(feats_of(merged) | feats_of(t))
            merged["features_known"] = merged.get("features_known") or t.get("features_known")
            for k in ("description", "insights", "park_walk_min", "rail", "vaad", "arnona", "top_floor", "board_events", "condition"):
                if not merged.get(k) and t.get(k):
                    merged[k] = t[k]
            if not merged.get("images"):
                merged["images"] = t.get("images") or []
        fit, no, unknown, warn = fit_of(merged, prefs, text)
        area, dist = area_of(merged, prefs, centers)
        insights, insights_from = merged.get("insights") or [], None
        if not insights and with_insights:
            near = min(((km_between(merged, o), o) for o in with_insights if km_between(merged, o) is not None),
                       key=lambda x: x[0], default=None)
            if near and near[0] <= 0.25:
                insights, insights_from = near[1]["insights"], round(near[0] * 1000)
        listed = parse_time(merged.get("listed_at"))
        # When the owner last touched the ad on its board, where a board says so (yad2's full ad, Homeless).
        touched = max((t for t in (parse_time(x.get("updated_at")) for x in [ad] + twins) if t), default=None)
        recent = [c for c in merged.get("changes") or [] if (parse_time(c["at"]) or now) >= recent_from]
        # New = we first saw it lately, and it is not just our own search getting wider (a board's first pull, or an
        # old ad that entered because the budget or rooms changed).
        is_new = ((ad["board"], merged["first_seen"]) not in widened
                  and (parse_time(merged["first_seen"]) or now) >= recent_from
                  and (listed is None or (now - listed).days <= 7))
        v = {k: merged.get(k) for k in (
            "id", "board", "url", "seller", "agency", "price", "rooms", "sqm", "floor", "top_floor", "type", "city",
            "hood", "street", "house_no", "lat", "lon", "description", "furniture", "entrance", "immediate",
            "on_pillars", "vaad", "arnona", "board_events", "park_walk_min", "rail", "first_seen", "last_seen",
            "gone_since", "status", "note", "summary", "changes")}
        v.update(
            images=merged.get("images") or [], features=sorted(feats_of(merged)),
            features_known=bool(merged.get("features_known")),
            boards=[{"id": x["id"], "board": x["board"], "url": x["url"], "price": x.get("price"), "seller": x.get("seller"),
                     "last_seen": x.get("last_seen"), "has_detail": bool(x.get("detail_at")), "images": len(x.get("images") or [])}
                    for x in [ad] + twins],
            loc_approx=merged.get("loc_approx"),
            # Which source each part of the merged ad came from.
            prov={"description": next((x["board"] for x in [ad] + twins if x.get("description")), None),
                  "features": [x["board"] for x in [ad] + twins if x.get("features_known")],
                  "location": merged.get("loc_approx") or (ad["board"] if merged.get("lat") else None),
                  "insights": ("near" if insights_from is not None else "own") if insights else None},
            fit=fit, no=no, unknown=unknown, warn=warn, flags=list(text["flags"]), area=area,
            condition=merged.get("condition"), entrance_flexible=bool(merged.get("entrance_flexible")),
            dist_km=round(dist, 2) if dist is not None else None,
            market=market_of(merged, pool, deal) if merged.get("type") not in boards.NOT_A_HOME else None,
            cost=cost_of(merged, text, deal), haggle=haggle_of(merged, now, deal),
            per_sqm=round(merged["price"] / merged["sqm"]) if deal == "sale" and merged.get("price") and merged.get("sqm") else None,
            insights=insights, insights_from=insights_from, near=near_of(merged, by_kind),
            days_listed=(now - listed).days if listed else None,
            listed_at=listed.isoformat(timespec="seconds") if listed else None,
            updated_at=touched.isoformat(timespec="seconds") if touched and (not listed or touched > listed) else None,
            is_new=is_new, recent=recent, has_detail=bool(merged.get("detail_at")),
        )
        # Marks are per person and seen by everyone on the profile: mine drive my filters, all of them the favorites.
        marks = ad.get("marks") or {}
        v["status"], v["note"] = (marks.get(me) or {}).get("status", ""), (marks.get(me) or {}).get("note", "")
        v["marks"] = [{"person": k, "name": who.get(k, "?"), "mine": k == me, "status": m.get("status", ""),
                       "note": m.get("note", ""), "at": m.get("at")} for k, m in marks.items() if m.get("status") or m.get("note")]
        v["fav_by"] = [m["name"] for m in v["marks"] if m["status"] in ("shortlist", "contacted", "visit")]
        if v["market"] and v["market"]["delta_pct"] <= -40:
            v["flags"].append("odd_price")  # a bait price, a share of a flat, key money: never a plain bargain
        v["score"], v["why"] = score_of(v, prefs, merged) if fit != "no" else (0, [])
        out.append(v)
    rank = {"yes": 0, "maybe": 1, "no": 2}
    out.sort(key=lambda v: (rank[v["fit"]], -v["score"], v["price"] or 0))
    return out


# ---------------- pulling from the boards ----------------

class BridgeError(RuntimeError):
    pass


# The extension (extension/) keeps asking the app "anything for me?" (POST /api/ext/poll). A request waits in JOBS
# until it asks; its answer comes back in a call of its own. Three requests exist: navigate, collect, notify.
EXT = {"seen": 0.0, "version": None}
JOBS = queue.Queue()
ANSWERS = {}  # job id -> {"event", "result"}
NO_BROWSER = ("התוסף של לוח אחד לא מחובר. צריך כרום פתוח במחשב הזה, עם התוסף מותקן ומופעל, "
              "והדף הזה פתוח בו. הוראות ההתקנה ב-README")


def browser_ready():
    """Is there a browser to read the boards with right now?"""
    if hasattr(LOCAL, "browser"):
        return True
    return time.time() - EXT["seen"] < 50


def ext_call(cmd, args, timeout):
    for _ in range(24):  # the app's page wakes the extension when it opens; give it a moment
        if browser_ready():
            break
        time.sleep(0.5)
    else:
        raise BridgeError(NO_BROWSER)
    job = {"id": secrets.token_hex(6), "cmd": cmd, "args": args}
    slot = ANSWERS[job["id"]] = {"event": threading.Event(), "result": None}
    JOBS.put(job)
    try:
        if not slot["event"].wait(timeout + 20):
            raise BridgeError("הדפדפן לא ענה בזמן. האם כרום עדיין פתוח?")
    finally:
        ANSWERS.pop(job["id"], None)
    res = slot["result"] or {}
    if res.get("ok"):
        return res.get("result")
    raise BridgeError(str(res.get("error") or "הדפדפן לא הצליח"))


def ext_poll(body):
    """One call from the extension. With "done": its answer to a request (it does not wait). Otherwise: hand it the
    next request, waiting up to 20 s for one. Several requests can be out at once, one per board."""
    EXT.update(seen=time.time(), version=str(body.get("version") or "")[:20])
    done = body.get("done")
    if isinstance(done, dict):
        slot = ANSWERS.get(done.get("id"))
        if slot:
            slot["result"] = done
            slot["event"].set()
        return {"job": None}
    end = time.time() + 20
    while time.time() < end:
        try:
            job = JOBS.get(timeout=max(0.1, end - time.time()))
        except queue.Empty:
            break
        if job["id"] in ANSWERS:  # still wanted (a request that timed out is dropped here)
            EXT["seen"] = time.time()
            return {"job": job}
    EXT["seen"] = time.time()
    return {"job": None}


def bridge(cmd, timeout=60, **args):
    """Ask the browser for one thing: navigate (url), collect (board, job) or notify (title, text, url)."""
    if hasattr(LOCAL, "browser"):
        return LOCAL.browser(cmd, args, timeout, BridgeError)
    return ext_call(cmd, args, timeout)


def run_job(board, job):
    out = bridge("collect", board=board, job=job, timeout=170)
    if isinstance(out, str):
        out = json.loads(out)
    if not isinstance(out, dict):
        raise BridgeError(f"תשובה לא צפויה מהדף: {str(out)[:150]}")
    return out


def wants_detail(rec, prefs, now):
    if fit_of(rec, prefs, boards.read_text(rec))[0] == "no" and rec.get("features_known"):
        return False
    basics = dict(rec, features_known=False, features=[])  # could it fit, before we know its features?
    quick = dict(prefs, features={}, hide=[], access={"need": False, "max_floor": 0})
    if fit_of(basics, quick, {"flags": []})[0] == "no":
        return False
    at = rec.get("detail_at")
    if not at:
        return True
    if any(c["field"] == "price" and c["at"] > at for c in rec.get("changes", [])):
        return True
    return parse_time(at) < parse_time(now) - timedelta(days=7)


SYNC = {"running": False, "profile": None, "steps": [], "done": [], "error": None, "finished": None}
STATE_FILE = ROOT / "data" / "state.json"
FIX_URL = {"yad2": "https://www.yad2.co.il/realestate/rent", "madlan": "https://www.madlan.co.il/for-rent",
           "komo": "https://account.komo.co.il/", "homeless": "https://www.homeless.co.il/rent/"}
# Madlan challenges a browser that comes back often. Fewer, evenly spaced visits keep it answering: at most one
# pull every REST_HOURS, and none at all while its human check is up (every knock on that page counts against us).
REST_HOURS = {"madlan": 6}
TROUBLE = {"human": "מבקש אימות אנושי: לפתוח ולעבור את הבדיקה", "login": "ההתחברות הפסיקה לעבוד: להתחבר שוב",
           "error": "הפסיק לענות"}


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"boards": {}}


def note_board(board, ok, why=None, detail=None):
    """Remember whether a board answered as it should (for Komo: whether we are signed in). The moment one that
    worked stops working, a desktop alert goes out, once; the app shows the state until it works again."""
    with LOCK:
        st = load_state()
        prev = st["boards"].get(board) or {}
        same = prev.get("ok") == ok and prev.get("why") == why
        st["boards"][board] = {"ok": ok, "why": why, "detail": detail, "since": prev.get("since") if same else now_iso(),
                               "worked_before": bool(prev.get("worked_before") or ok), "checked": now_iso(),
                               "last_ok": now_iso() if ok else prev.get("last_ok")}
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    if prev.get("ok") and not ok:
        try:
            bridge("notify", title="לוח אחד", text=f"{boards.BOARDS[board]}: {TROUBLE.get(why, TROUBLE['error'])}", url=FIX_URL[board])
        except BridgeError:
            pass  # the app still shows it


HUMAN_CHECK = "הלוח מבקש אימות אנושי. פתחו אותו בכרום, עברו את הבדיקה בעצמכם, ואז סנכרנו שוב"
# How each board is read. "pages": the tab itself goes from page to page, the way a person browses (Madlan checks
# the pace and the kind of request). "fetch": one page is opened and the script inside it reads the rest.
PACE = {"yad2": {"details": 60, "batch": 12}, "madlan": {"details": 5, "page_gap": 4, "ad_gap": 7}, "komo": {"details": 25, "batch": 8, "page_gap": 2.5},
        "homeless": {"details": 20, "batch": 8}}


def komo_feed(url, say):
    """Komo shows the first 20 ads of a search to everyone and asks to sign in for the rest. So: the search itself
    (already private-only when the profile asks for that), and the same search with an elevator, which tells which of
    the ads have one. Further pages are read only when the user is signed in to Komo in this Chrome."""
    def walk(extra, cap):
        rows, total, page = [], None, 1
        while True:
            bridge("navigate", url=url + extra + (f"&currPage={page}" if page > 1 else ""))
            res = run_job("komo", {"mode": "page"})
            if res.get("login"):
                signed["in"] = False
                return rows, total, False, "login"
            if "ads" not in res:
                return rows, total, False, "; ".join(res.get("errors") or ["קומו לא החזיר דף"])
            rows += res["ads"]
            total = res.get("total")
            if signed["in"] is None:
                signed["in"] = bool(res.get("signedIn"))
            pages = max(1, math.ceil((total or len(rows)) / 20))
            if page >= min(pages, cap):
                return rows, total, page >= pages, None
            page += 1
            time.sleep(PACE["komo"]["page_gap"])

    signed = {"in": None}
    everything, total, complete, why = walk("", 6)
    if not everything and why:
        raise BridgeError("קומו מבקש התחברות" if why == "login" else why)
    if why == "login":
        say(f"קומו: בלי התחברות מוצגות רק 20 מתוך {total}. התחברות לקומו בכרום תפתח את השאר")
    time.sleep(PACE["komo"]["page_gap"])
    lift, _, lift_all, _ = walk("&yesElevator=1", 1)
    return {"ads": list({r["id"]: r for r in everything}.values()), "total": total, "complete": complete,
            "private_search": "privateOnly=1" in url, "elevator": [r["id"] for r in lift], "elevator_complete": lift_all,
            "signed_in": bool(signed["in"]),
            "errors": [] if why in (None, "login") else [why]}


def pull_feed(board, url, city, say):
    if board == "komo":
        return komo_feed(url, say)
    if board == "homeless":
        bridge("navigate", url=url)
        res = run_job(board, {"mode": "page"})
        if "ads" not in res:
            raise BridgeError("; ".join(res.get("errors") or []) or "הלוח לא החזיר מודעות")
        if res.get("hasNext"):
            say("הומלס: נקרא העמוד הראשון בלבד")
        return {"ads": res["ads"], "total": None, "complete": not res.get("hasNext"), "errors": []}
    if board != "madlan":
        bridge("navigate", url=url)
        feats = [f for f in YAD2_FEATURES if not ("/forsale" in url and f == "pets")]  # no such filter for a purchase
        res = run_job(board, {"mode": "feed", "features": feats, "maxPages": 8})
        if res.get("blocked"):
            # A browser the board has not seen before first gets a "checking your browser" page that passes by
            # itself in a few seconds. Wait and read the open page once more; nothing new is asked of the board.
            # A real check (one that wants a person) is still there afterwards, and is reported as such.
            time.sleep(9)
            res = run_job(board, {"mode": "feed", "features": feats, "maxPages": 8})
        if "ads" not in res:
            raise BridgeError(HUMAN_CHECK if res.get("blocked") else "; ".join(res.get("errors") or []) or "הלוח לא החזיר מודעות")
        return res
    ads, total, page, pages = {}, None, 1, 1
    while True:
        bridge("navigate", url=url + (f"&page={page}" if page > 1 else ""))
        res = run_job(board, {"mode": "page", "city": boards.plain_name(city)})
        if "ads" not in res:
            if page == 1:
                raise BridgeError(HUMAN_CHECK if res.get("blocked") else "; ".join(res.get("errors") or []) or "הלוח לא החזיר מודעות")
            return {"ads": list(ads.values()), "total": total, "complete": False, "errors": res.get("errors") or []}
        ads.update({a["id"]: a for a in res["ads"]})
        total = res.get("total")
        pages = max(1, math.ceil((total or 0) / 50))
        if page >= min(pages, 6):
            return {"ads": list(ads.values()), "total": total, "complete": page >= pages, "errors": []}
        page += 1
        time.sleep(PACE[board]["page_gap"])


def pull_details(board, ids):
    """{native id: the board's full record}, whether the board refused, and errors. The tab must be on that board."""
    if board != "madlan":
        out = run_job(board, {"mode": "details", "ids": ids})
        return out.get("items") or {}, bool(out.get("blocked")), out.get("errors") or []
    items, errors = {}, []
    for n, native in enumerate(ids):
        if n:
            time.sleep(PACE[board]["ad_gap"])
        bridge("navigate", url="https://www.madlan.co.il/listings/" + native)
        out = run_job(board, {"mode": "ad", "id": native})
        if out.get("blocked"):
            return items, True, errors + (out.get("errors") or [])
        if out.get("item"):
            items[native] = out["item"]
        errors += out.get("errors") or []
    return items, False, errors


def normalize_item(board, raw, res, deal="rent"):
    norm = _normalize_item(board, raw, res, deal)
    if deal == "sale" and norm.get("price") and norm["price"] < 50000:
        norm["price"] = None  # "1,234" on a flat for sale is an owner who does not want to say
    return norm


def _normalize_item(board, raw, res, deal):
    if board == "yad2":
        return boards.yad2_item(raw, {f: set(t) for f, t in res["features"].items()} if res.get("mapOk") else None)
    if board == "komo":
        return boards.komo_item(raw, res["private_search"], set(res["elevator"]), res["elevator_complete"])
    if board == "homeless":
        return boards.homeless_item(raw, deal)
    return boards.madlan_item(raw)


def save_details(pid, board, items, now):
    with LOCK:
        p = load_profile(pid)
        if p.get("store"):
            p = load_profile(p["store"])  # the ad belongs to the city's store
        done = 0
        for native, d in items.items():
            norm = getattr(boards, board + "_detail")(d)
            norm["id"] = f"{board}:{native}"
            if norm["id"] in p["ads"]:
                merge_ad(p, norm, now, from_detail=True)
                done += 1
        save_profile(p)
    return done


def sync_board(p, board, city, now, say):
    prefs, he = p["prefs"], boards.BOARDS[board]
    deal = boards.deal_of(prefs)
    url = getattr(boards, board + "_url")(city, prefs, MARGIN[deal])
    say(f"{he}: פותח את החיפוש")
    res = pull_feed(board, url, city, say)
    errors = list(res.get("errors") or [])
    seen, new, changed = set(), 0, 0
    with LOCK:
        p = load_profile(p["id"])
        for raw in res["ads"]:
            norm = normalize_item(board, raw, res, deal)
            seen.add(norm["id"])
            r = merge_ad(p, norm, now)
            new += r == "new"
            changed += r == "changed"
        # A list that stops at its page limit is still a full read when the ads seen (the lists and the map
        # together) are exactly as many as the board says the search holds: nothing can be missing.
        complete = (bool(res.get("complete")) or bool(res.get("total") and len(seen) == res["total"])) and not errors
        gone = mark_gone(p, board, seen, now) if complete else 0
        save_profile(p)
    say(f"{he}: {len(seen)} מודעות" + (f" מתוך {res['total']}" if res.get("total") and res["total"] > len(seen) else "")
        + f", {new} חדשות, {changed} השתנו, {gone} ירדו")
    if board in ("komo", "homeless"):
        with GEO_LOCK:  # one address question a second in all, also when two boards finish together
            placed = locate(p["id"], city, say)
        if placed:
            say(f"{he}: {placed} כתובות מוקמו על המפה")
        with LOCK:
            p = load_profile(p["id"])
    live = [r for r in p["ads"].values() if not r.get("gone_since")]
    dup = find_duplicates(live)
    twins = set(dup) | set(dup.values())  # another board already has their full ad
    want = [r["native_id"] for r in live if r["board"] == board and wants_detail(r, prefs, now)
            and not (board != "yad2" and r["id"] in twins and r.get("features_known"))]
    if board == "madlan":
        want = [n for n in want if f"madlan:{n}" not in twins]
    if prefs.get("lists_only"):
        want = []  # a city store: full ads are read one by one, when somebody opens one
    want, detailed, size = want[:PACE[board]["details"]], 0, PACE[board].get("batch", 5)
    for i in range(0, len(want), size):
        say(f"{he}: קורא מודעות מלאות ({min(i + size, len(want))}/{len(want)})")
        items, refused, errs = pull_details(board, want[i:i + size])
        errors += errs
        detailed += save_details(p["id"], board, items, now)
        if refused or (errs and not items):
            say(f"{he}: הלוח הפסיק לענות, השאר בסנכרון הבא")
            break
    out = {"board": board, "url": url, "seen": len(seen), "total": res.get("total"), "new": new, "changed": changed, "gone": gone,
           "detailed": detailed, "complete": complete, "errors": errors[:5]}
    if board == "komo":
        out["signed_in"] = res["signed_in"]
    return out


def read_one(pid, ad_id):
    """The full ad of one stored ad, now: what the "read the full ad" button does. One page view."""
    with LOCK:
        if SYNC["running"]:
            raise BridgeError("סנכרון רץ עכשיו, נסו שוב כשיסתיים")
        rec = load_profile(pid)["ads"].get(ad_id)
    if not rec:
        raise KeyError("no such ad")
    board, native = rec["board"], rec["native_id"]
    if board not in boards.BOARDS:
        raise BridgeError("מודעה שהודבקה: כל מה שיש עליה כבר כאן")
    if board != "madlan":
        bridge("navigate", url=rec["url"])
    items, refused, errs = pull_details(board, [native])
    if refused:
        raise BridgeError(HUMAN_CHECK)
    if not items:
        raise BridgeError("; ".join(errs) or "הלוח לא החזיר את המודעה")
    save_details(pid, board, items, now_iso())


# ---------------- an address without a pin (Komo) ----------------

GEO_FILE = ROOT / "data" / "geocode.json"


def locate(pid, city, say=lambda t: None, only=None):
    """Give coordinates to ads that came with an address only. OpenStreetMap's Nominatim, one question a second (its
    rule), answers kept in data/geocode.json. No street match: the neighborhood's centre, marked as approximate."""
    import urllib.parse
    import urllib.request
    try:
        cache = json.loads(GEO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    hoods = {h["name"]: h for h in city["hoods"]}
    with LOCK:
        todo = [(r["id"], r.get("street"), r.get("house_no"), r.get("hood")) for r in load_profile(pid)["ads"].values()
                if not r.get("lat") and not r.get("gone_since") and (only is None or r["id"] in only)]
    found, asked = {}, 0
    for ad_id, street, house, hood in todo:
        hit = None
        if street:
            q = f"{street} {house or ''}".strip() + f", {boards.plain_name(city)}, ישראל"
            if q not in cache and asked < 40:
                if asked:
                    time.sleep(1.1)
                asked += 1
                url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "il"})
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "apartment-board/1.0"}), timeout=20) as r:
                        ans = json.loads(r.read())
                    cache[q] = [float(ans[0]["lat"]), float(ans[0]["lon"])] if ans else None
                except (OSError, ValueError, KeyError, IndexError):
                    pass
            if cache.get(q) and km_between({"lat": cache[q][0], "lon": cache[q][1]}, city) is not None \
                    and km_between({"lat": cache[q][0], "lon": cache[q][1]}, city) < 12:
                hit = {"lat": cache[q][0], "lon": cache[q][1], "loc_approx": "street"}
        if not hit:
            h = hoods.get(hood) or next((v for k, v in hoods.items() if hood and (hood in k or k in hood)), None)
            if h:
                hit = {"lat": h["lat"], "lon": h["lon"], "loc_approx": "hood"}
        if hit:
            found[ad_id] = hit
    GEO_FILE.parent.mkdir(exist_ok=True)
    GEO_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with LOCK:
        p = load_profile(pid)
        for ad_id, hit in found.items():
            if ad_id in p["ads"]:
                p["ads"][ad_id].update(hit)
        save_profile(p)
    return len(found)


def sync(pid, say=print, only=None, done=None):
    """Pull the profile's search. The boards are read side by side, each in its own tab and at its own pace: they
    are different sites, so one board never gets more than one request at a time.
    only: one board's name, to pull just that board (the others keep what they have)."""
    with LOCK:
        p = load_profile(pid)
    if p.get("store"):  # a search over a city store: it is the city that is read
        return sync(p["store"], say, only, done)
    city, now = CITIES[p["prefs"]["city"]], now_iso()
    old_ext = tuple(int(x) for x in re.findall(r"\d+", EXT["version"] or "0")[:2]) < (1, 1)
    if boards.deal_of(p["prefs"]) == "sale" and not hasattr(LOCAL, "browser") and browser_ready() and old_ext:
        # The extension from before 1.1 reads every yad2 and Homeless tab as a rent search.
        raise BridgeError("חיפוש לקנייה צריך את התוסף המעודכן: ב-chrome://extensions לוחצים על חץ הרענון של "
                          "\"לוח אחד: קורא הלוחות\", ואז מרעננים את הדף הזה")

    def one(board):
        st = load_state()["boards"].get(board) or {}
        he = boards.BOARDS[board]
        if st.get("ok") is False and st.get("why") == "human" and not st.get("retry"):
            say(f"{he}: מחכה לך. אחרי שעברת את הבדיקה באתר של הלוח, לחצו \"פתרתי\" כאן, והסנכרון הבא ינסה שוב")
            return {"board": board, "skipped": "human"}
        rest = REST_HOURS.get(board)
        last_ok = parse_time(st.get("last_ok"))
        if rest and st.get("ok") and last_ok and datetime.now() - last_ok < timedelta(hours=rest):
            ago = (datetime.now() - last_ok).total_seconds() / 3600
            say(f"{he}: נמשך לפני {ago:.1f} שעות. נמשך פעם ב-{rest} שעות כדי שלא יחסום, המודעות שלו נשארות")
            return {"board": board, "skipped": "resting"}
        try:
            res = sync_board(p, board, city, now, say)
            if board == "komo" and not res["signed_in"]:
                note_board(board, False, "login")
            else:
                note_board(board, True)
            return res
        except BridgeError as e:
            say(f"{he}: לא הצליח ({e})")
            note_board(board, False, "human" if "אימות אנושי" in str(e) else "login" if "התחברות" in str(e) else "error", str(e))
            return {"board": board, "error": str(e)}
        except Exception as e:  # a fault in one board's code must not stop the other boards
            say(f"{he}: תקלה אצלנו ({type(e).__name__}: {e})")
            return {"board": board, "error": f"{type(e).__name__}: {e}"}

    todo = [b for b in boards.BOARDS if not only or b == only]
    got = {}
    def run(b):
        got[b] = one(b)
        if done:
            done(b)

    threads = [threading.Thread(target=run, args=(b,), daemon=True) for b in todo]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    results = [got.get(b) or {"board": b, "error": "לא הסתיים"} for b in todo]
    if hasattr(LOCAL, "after_sync"):
        LOCAL.after_sync()
    with LOCK:
        p = load_profile(pid)
        p["meta"]["last_sync"] = now
        p["meta"]["syncs"] = (p["meta"].get("syncs") or [])[-49:] + [{"at": now, "boards": results}]
        save_profile(p)
    if all("error" in r for r in results):
        raise BridgeError(results[0]["error"])
    return results


def start_sync(pid, only=None):
    with LOCK:
        if SYNC["running"]:
            return False
        SYNC.update(running=True, profile=pid, steps=[], done=[], error=None, finished=None)

    def work():
        try:
            sync(pid, say=lambda t: SYNC["steps"].append(t), only=only, done=lambda b: SYNC["done"].append(b))
        except Exception as e:  # the thread must always release the flag
            SYNC["error"] = str(e)
        finally:
            SYNC.update(running=False, finished=now_iso())

    threading.Thread(target=work, daemon=True).start()
    return True


def sync_through_app(pid, only=None):
    """`python app.py sync` from a shell: the running app is the one connected to Chrome, so ask it to pull and
    print its steps as they come."""
    import urllib.error
    import urllib.request

    def call(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/{path}", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                why = json.loads(e.read()).get("error")
            except ValueError:
                why = None
            sys.exit(f"הסנכרון לא התחיל: {why or e.code}")
        except OSError:
            sys.exit("האפליקציה לא רצה. מפעילים אותה (start.cmd), משאירים אותה פתוחה בכרום, ומנסים שוב.")

    if call(f"profiles/{pid}/sync", {"board": only}).get("error"):
        sys.exit("סנכרון אחר כבר רץ")
    shown = 0
    while True:
        s = call(f"sync?for={pid}")
        for line in s["steps"][shown:]:
            print(line, flush=True)
        shown = len(s["steps"])
        if not s["running"]:
            break
        time.sleep(1.5)
    if s.get("error"):
        sys.exit(f"הסנכרון לא הצליח: {s['error']}")


def paste_ad(pid, text, url=None):
    """An ad the person brought as text, from anywhere. Nothing is fetched for it; it is read, placed on the map by
    its street or neighborhood, and from then on it is ranked and compared like any other ad."""
    text = str(text or "").strip()
    if len(text) < 15:
        raise ValueError("צריך את הטקסט של המודעה")
    with LOCK:
        p = load_profile(pid)
        city = CITIES[p["prefs"]["city"]]
        norm, missing = boards.pasted_item(text, url, p["prefs"]["city"], [h["name"] for h in city["hoods"]], boards.deal_of(p["prefs"]))
        ad_id, now = norm["id"], now_iso()
        known = ad_id in p["ads"]
        merge_ad(p, norm, now, from_detail=True)
        p["ads"][ad_id].update(last_seen=now, listed_at=p["ads"][ad_id].get("listed_at") or now)
        save_profile(p)
    with GEO_LOCK:
        locate(pid, city, only={ad_id})
    elsewhere = sorted(n for n in CITIES if n != p["prefs"]["city"] and n != "שדרות"  # also the word for a boulevard
                       and re.search(r"(?<![֐-׿])[בלמ]?" + re.escape(n) + r"(?![֐-׿])", text))[:3]
    return {"id": ad_id, "known": known, "missing": missing, "other_city": elsewhere}


def remove_pasted(pid, ad_id):
    with LOCK:
        p = load_profile(pid)
        if ad_id not in p["ads"] or p["ads"][ad_id]["board"] in boards.BOARDS:
            raise KeyError("no such ad")
        del p["ads"][ad_id]
        save_profile(p)


def set_fields(pid, ad_id, person=people.OWNER, status=None, note=None, summary=None):
    """A person's own mark on an ad (status, note), or a short summary of the ad written for it."""
    if status is not None and status not in STATUSES:
        raise ValueError("status")
    with LOCK:
        p = load_profile(pid)
        rec = p["ads"].get(ad_id)
        if not rec:
            raise KeyError("no such ad")
        mark = rec.setdefault("marks", {}).setdefault(person, {})
        if status is not None:
            mark["status"] = status
        if note is not None:
            mark["note"] = str(note)[:2000]
        if status is not None or note is not None:
            mark["at"] = now_iso()
        if summary is not None:
            rec["summary"] = str(summary)[:2000]
        save_profile(p)


# ---------------- the app ----------------

def maps_key():
    """A Google Maps Embed key for Street View inside the app, if the person put one in data/maps-key.txt. A browser
    key is visible to the page that uses it by design: restrict it at Google to http://127.0.0.1:7461/* and to the
    Maps Embed API only. Without a key the app shows a link to Street View instead."""
    try:
        return MAPS_KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


LAN = False
TAILNET = ipaddress.ip_network("100.64.0.0/10")  # Tailscale addresses: the user's own private network between devices
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#fbf6ec"/>'
        '<rect x="14" y="14" width="36" height="36" rx="9" fill="#ff6542" stroke="#24201a" stroke-width="3" transform="rotate(-8 32 32)"/></svg>')


def open_in_chrome(url):
    """Open the app in Chrome (the browser that has the extension), in its own window where possible."""
    tries = {"win32": [f'start "" chrome --app={url}'], "darwin": [f'open -na "Google Chrome" --args --app={url}']}.get(
        sys.platform, [f"google-chrome --app={url}", f"google-chrome-stable --app={url}", f"chromium --app={url}"])
    for cmd in tries:
        try:
            if subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    webbrowser.open(url)


def lan_ip():
    """This PC's address on the home network (no packet is sent: the socket only picks the route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def at_home(ip):
    return ip.is_private or ip in TAILNET


class Refused(Exception):
    def __init__(self, text, code=403):
        super().__init__(text)
        self.code = code


class Handler(BaseHTTPRequestHandler):
    is_local = True
    is_ext = False
    person = None

    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json; charset=utf-8", headers=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # No Referrer-Policy header on purpose: OpenStreetMap's tile servers refuse requests that do not say which
        # app is asking. Links' secrets sit after the "#", which a browser never sends to any server.
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        """Which devices may reach the app at all. Always this PC. With --lan also devices on the home network or
        the user's Tailscale network, and only when they address the app by its network number: a web page elsewhere
        cannot then reach it through a visitor's browser (its requests carry another site's Origin, or a name
        instead of the number). Sets self.is_local. What a device may then SEE is decided by who is signed in."""
        client = ipaddress.ip_address(self.client_address[0])
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        origin = self.headers.get("Origin")
        # Our own extension, in a browser on this computer. A web page cannot send this header to us (a page from
        # another site would first have to ask permission, which the app never gives), nor an extension's Origin.
        self.is_ext = (client.is_loopback and host == "127.0.0.1" and bool(self.headers.get("X-Luach-Extension"))
                       and (origin or "").startswith("chrome-extension://") and self.path == "/api/ext/poll")
        if self.is_ext:
            self.is_local = True
            return True
        if origin is not None and origin.split("//")[-1] != (self.headers.get("Host") or ""):
            return False
        self.is_local = client.is_loopback
        if self.is_local:
            return host in ("127.0.0.1", "localhost")
        try:
            return LAN and at_home(client) and at_home(ipaddress.ip_address(host))
        except ValueError:
            return False

    def who(self):
        """The person behind this request: the owner at this PC, otherwise whoever this device's cookie belongs to."""
        if self.is_local:
            return people.OWNER
        m = re.search(r"(?:^|;\s*)sid=([\w-]+)", self.headers.get("Cookie") or "")
        return people.person_of_session(m.group(1)) if m else None

    def base_url(self):
        """The address other devices use for this app, for links that are sent to them."""
        if not self.is_local:
            return "http://" + self.headers.get("Host")
        if not LAN:
            raise Refused("קישורים למכשירים אחרים עובדים רק כשהאפליקציה רצה במצב רשת (start-lan.cmd)", 400)
        return f"http://{lan_ip()}:{PORT}"

    def profile(self, pid):
        with LOCK:
            p = load_profile(pid)
        if self.person != people.OWNER and self.person not in p.get("members", []):
            raise KeyError("no such profile")
        return p

    def owner_only(self):
        if self.person != people.OWNER:
            raise Refused("רק מי שפתח את החיפוש יכול לעשות את זה")

    def route(self, method, body=None):
        parts = [x for x in self.path.split("?")[0].split("/") if x]
        if method == "GET" and not parts:
            return self.send((ROOT / "ui" / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
        if method == "GET" and parts == ["lang.js"]:
            # every language file the app has, as one script the page loads before its own
            langs = {}
            for f in sorted((ROOT / "ui" / "lang").glob("*.json")):
                try:
                    langs[f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    pass
            return self.send(("window.LANGS = " + json.dumps(langs, ensure_ascii=False) + ";").encode("utf-8"),
                             ctype="text/javascript; charset=utf-8")
        if method == "GET" and parts == ["icon.svg"]:
            return self.send(ICON.encode(), ctype="image/svg+xml")
        if method == "GET" and parts == ["manifest.webmanifest"]:
            return self.send({"name": "לוח אחד", "short_name": "לוח אחד", "start_url": "/", "display": "standalone", "dir": "rtl",
                              "lang": "he", "background_color": "#fbf6ec", "theme_color": "#fbf6ec",
                              "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]},
                             ctype="application/manifest+json")
        if parts[:1] != ["api"]:
            return self.send({"error": "not found"}, 404)
        parts = parts[1:]
        me = self.person
        if parts == ["ext", "poll"]:
            if not (self.is_ext and method == "POST"):
                return self.send({"error": "not found"}, 404)
            return self.send(ext_poll(body))

        # ---- open to any device that can reach the app: nothing private here ----
        if method == "GET" and parts == ["meta"]:
            return self.send({"cities": [{"name": c["name"], "lat": c["lat"], "lon": c["lon"], "hoods": c["hoods"]} for c in CITIES.values()],
                              "features": boards.FEATURES, "types": boards.TYPES, "boards": dict(boards.BOARDS, **boards.OTHER), "sync_boards": list(boards.BOARDS), "kinds": KINDS,
                              "deals": boards.DEALS,
                              # the Street View key works only from this PC's own address (set at Google)
                              "maps_key": maps_key() if self.is_local else None, "local": self.is_local})
        if method == "GET" and parts == ["me"]:
            return self.send({"person": me, "name": people.names().get(me) if me else None, "owner": me == people.OWNER,
                              "local": self.is_local, "lan": LAN,
                              # only the person at this computer needs to know whether the boards can be read now
                              "browser": browser_ready() if self.is_local else None})
        ip = self.client_address[0]
        if parts[:1] in (["link"], ["join"], ["shared"]) and people.slow_down(ip):
            return self.send({"error": "יותר מדי ניסיונות. נסו שוב בעוד כמה דקות"}, 429)
        if method == "GET" and len(parts) == 2 and parts[0] == "link":
            rec = people.peek(parts[1])
            if not rec or rec["kind"] == "ad":
                people.wrong(ip)
                return self.send({"error": "הקישור לא תקף או שכבר נעשה בו שימוש"}, 404)
            names = people.names()
            out = {"kind": rec["kind"], "by": names.get(rec["by"])}
            if rec["kind"] == "invite":
                out["profile_name"] = load_profile(rec["profile"])["name"]
            else:
                out["person_name"] = names.get(rec["person"])
            return self.send(out)
        if method == "POST" and parts == ["join"]:
            token = str(body.get("token") or "")
            rec = people.peek(token)
            if not rec or rec["kind"] == "ad":
                people.wrong(ip)
                return self.send({"error": "הקישור לא תקף או שכבר נעשה בו שימוש"}, 404)
            if rec["kind"] == "invite":
                person = me or people.add_person(body.get("name"))  # a device already signed in joins as itself
                with LOCK:
                    p = load_profile(rec["profile"])
                    if person != people.OWNER and person not in p.setdefault("members", []):
                        p["members"].append(person)
                    save_profile(p)
            else:
                person = rec["person"]
            people.use(token)
            cookie = {}
            if person != me:
                sid = people.new_session(person, self.headers.get("User-Agent"))
                cookie = {"Set-Cookie": f"sid={sid}; Max-Age={people.SESSION_DAYS * 86400}; Path=/; HttpOnly; SameSite=Lax"}
            return self.send({"ok": True, "profile": rec.get("profile")}, headers=cookie)
        if method == "GET" and len(parts) == 2 and parts[0] == "shared":
            rec = people.peek(parts[1])
            if not rec or rec["kind"] != "ad":
                people.wrong(ip)
                return self.send({"error": "הקישור לא תקף"}, 404)
            with LOCK:
                p = load_profile(rec["profile"])
            v = next((x for x in build_views(p, None) if x["id"] == rec["ad"] or any(b["id"] == rec["ad"] for b in x["boards"])), None)
            if not v:
                return self.send({"error": "המודעה כבר לא קיימת"}, 404)
            v.update(status="", note="", marks=[], fav_by=[])  # one ad, without anyone's notes
            return self.send({"ad": v, "by": people.names().get(rec["by"]), "hoods": bool(p["prefs"]["hoods"]),
                              "deal": boards.deal_of(p["prefs"])})

        # ---- everything below needs a person ----
        if me is None:
            return self.send({"error": "login"}, 401)
        if method == "POST" and parts == ["me", "name"]:
            people.rename(me, body.get("name"))
            return self.send({"ok": True})
        if method == "POST" and parts == ["me", "attach"]:
            return self.send({"url": f"{self.base_url()}/#/join/{people.new_link('attach', me, person=me)}", "minutes": 15})
        if method == "GET" and parts == ["profiles"]:
            return self.send(list_profiles(me))
        if method == "GET" and parts == ["sync"]:
            sid = None
            m = re.search(r"[?&]for=([a-z0-9-]{1,40})", self.path)
            if m:
                try:
                    sid = self.profile(m.group(1)).get("store")
                except KeyError:
                    sid = None
            if not sid:
                return self.send(SYNC)
            # a search over a city store: its own city's reading, or its place in the line
            q = queue_state(sid)
            if SYNC["profile"] == sid and (SYNC["running"] or not q["pos"]):
                return self.send(dict(SYNC, queue=q))
            ahead = (q["pos"] or 1) - 1
            line = (f"העיר שלך הבאה בתור, עוד כ-{q['wait_min']} דקות" if not ahead
                    else f"בתור: עיר אחת לפנייך, עוד כ-{q['wait_min']} דקות" if ahead == 1
                    else f"בתור: {ahead} ערים לפנייך, עוד כ-{q['wait_min']} דקות")
            steps = [line] if q["pos"] else []
            return self.send({"running": bool(q["pos"]), "profile": sid, "steps": steps, "done": [], "error": None, "finished": None, "queue": q})
        if method == "POST" and len(parts) == 3 and parts[0] == "boards" and parts[2] == "retry" and parts[1] in boards.BOARDS:
            self.owner_only()
            with LOCK:  # the person says the human check is solved: the next sync may try that board again
                st = load_state()
                st["boards"].setdefault(parts[1], {})["retry"] = True
                STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
            return self.send({"ok": True})
        if method == "POST" and parts == ["profiles"]:
            self.owner_only()
            p = create_profile(body.get("name"), body.get("prefs") or {})
            return self.send({"id": p["id"]})
        if len(parts) >= 2 and parts[0] == "profiles":
            pid = parts[1]
            p = self.profile(pid)
            if method == "GET" and len(parts) == 2:
                city, names, seen = CITIES[p["prefs"]["city"]], people.names(), people.last_seen()
                return self.send({"id": p["id"], "name": p["name"], "prefs": p["prefs"], "meta": p["meta"], "store": p.get("store"),
                                  "city": {"name": city["name"], "lat": city["lat"], "lon": city["lon"]},
                                  "centers": [h for h in city["hoods"] if h["name"] in p["prefs"]["hoods"]],
                                  "places": load_places(city), "kinds": KINDS, "board_state": load_state()["boards"],
                                  "fix_url": FIX_URL, "rest_hours": REST_HOURS,
                                  "shared": bool(p.get("store")) and dict(queue_state(p["store"]), fresh_hours=FRESH_HOURS,
                                                                              age_hours=store_age_hours(p["store"])),
                                  "people": [{"id": x, "name": names.get(x, "?"), "owner": x == people.OWNER, "seen": seen.get(x)}
                                             for x in [people.OWNER] + p.get("members", [])],
                                  "ads": build_views(p, me)})
            if method == "POST" and len(parts) == 4 and parts[2] == "ads":
                set_fields(pid, parts[3], me, body.get("status"), body.get("note"))
                return self.send({"ok": True})
            if method == "POST" and len(parts) == 5 and parts[2] == "ads" and parts[4] == "share":
                if parts[3] not in p["ads"]:
                    raise KeyError("no such ad")
                return self.send({"url": f"{self.base_url()}/#/ad/{people.new_link('ad', me, profile=pid, ad=parts[3])}", "days": 30})
            # From here on: the owner only (a member looks, marks and shares; the search itself is the owner's).
            self.owner_only()
            if method == "POST" and parts[2:] == ["invite"]:
                return self.send({"url": f"{self.base_url()}/#/join/{people.new_link('invite', me, profile=pid)}", "days": 7})
            if method == "POST" and len(parts) == 5 and parts[2] == "members" and parts[4] == "remove":
                with LOCK:
                    p = load_profile(pid)
                    p["members"] = [m for m in p.get("members", []) if m != parts[3]]
                    save_profile(p)
                if not any(parts[3] in json.loads(f.read_text(encoding="utf-8")).get("members", []) for f in PROFILES.glob("*.json")):
                    people.end_sessions(parts[3])  # no search left for them: their devices are signed out
                return self.send({"ok": True})
            if method == "POST" and parts[2:] == ["places"]:
                try:
                    return self.send({"count": len(fetch_places(CITIES[p["prefs"]["city"]]))})
                except OSError as e:
                    return self.send({"error": f"OpenStreetMap לא ענה: {e}"}, 502)
            if method == "POST" and parts[2:] == ["prefs"]:
                with LOCK:
                    p = load_profile(pid)
                    old = p["prefs"]
                    # A search stays what it was opened as: rent and sale ads never share one board.
                    p["prefs"] = clean_prefs(dict(body.get("prefs") or {}, deal=old.get("deal")))
                    if body.get("name"):
                        p["name"] = str(body["name"]).strip()[:40]
                    if p.get("store"):
                        p["store"] = ensure_store(p["prefs"])  # another city: another store
                    save_profile(p)
                wider = any(old.get(k) != p["prefs"].get(k) for k in ("city", "price_max", "price_min", "rooms_min", "rooms_max"))
                return self.send({"ok": True, "needs_sync": wider})
            if method == "POST" and parts[2:] == ["sync"]:
                if p.get("store"):  # a search over a city store does not pull: its city takes a place in the line
                    pos = enqueue(p["store"])
                    return self.send({"ok": True, "queued": pos, "fresh": pos == 0, "queue": queue_state(p["store"])})
                only = body.get("board") if body.get("board") in boards.BOARDS else None
                return self.send({"ok": True} if start_sync(pid, only) else {"error": "סנכרון אחר כבר רץ"}, 200 if not SYNC["running"] or SYNC["profile"] == pid else 409)
            if method == "POST" and parts[2:] == ["paste"]:
                self.owner_only()
                try:
                    return self.send(paste_ad(pid, body.get("text"), body.get("url")))
                except ValueError as e:
                    return self.send({"error": str(e)}, 400)
            if method == "POST" and len(parts) == 5 and parts[2] == "ads" and parts[4] == "remove":
                self.owner_only()
                remove_pasted(pid, parts[3])
                return self.send({"ok": True})
            if method == "POST" and len(parts) == 5 and parts[2] == "ads" and parts[4] == "detail":
                try:
                    read_one(pid, parts[3])
                except BridgeError as e:
                    return self.send({"error": str(e)}, 502)
                return self.send({"ok": True})
        return self.send({"error": "not found"}, 404)

    def handle_one(self, method):
        if not self.allowed():
            return self.send({"error": "local only"}, 403)
        self.person = self.who()
        body = None
        if method == "POST":
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self.send({"error": "local only"}, 403)
            try:
                limit = 30_000_000 if self.is_ext else 200_000  # the extension hands back whole result pages
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), limit)) or b"{}")
            except ValueError:
                return self.send({"error": "bad JSON"}, 400)
            if not isinstance(body, dict):
                return self.send({"error": "bad JSON"}, 400)
        try:
            self.route(method, body)
        except KeyError:
            self.send({"error": "not found"}, 404)
        except ValueError as e:
            self.send({"error": f"bad value: {e}"}, 400)
        except Refused as e:
            self.send({"error": str(e)}, e.code)

    def do_GET(self):
        self.handle_one("GET")

    def do_POST(self):
        self.handle_one("POST")


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("--lan", action="store_true", help="also answer other devices on the home network")
    s.add_argument("--open", action="store_true", help="open the app in Chrome once it is up")
    s.add_argument("--shared", action="store_true", help="a new search looks through its city's shared store; cities are read in turn")
    s = sub.add_parser("sync")
    s.add_argument("profile")
    s.add_argument("board", nargs="?", choices=list(boards.BOARDS), help="only this board")
    s = sub.add_parser("list")
    s.add_argument("profile")
    s.add_argument("--all", action="store_true")
    s = sub.add_parser("set")
    s.add_argument("profile")
    s.add_argument("ad")
    s.add_argument("--status")
    s.add_argument("--note")
    s.add_argument("--summary")
    args = ap.parse_args()
    if args.cmd == "sync":
        if not hasattr(LOCAL, "browser"):
            return sync_through_app(args.profile, args.board)
        try:
            sync(args.profile, only=args.board)
        except (BridgeError, KeyError) as e:
            sys.exit(f"הסנכרון לא הצליח: {e}")
    elif args.cmd == "list":
        for v in build_views(load_profile(args.profile)):
            if v["gone_since"] or (v["fit"] == "no" and not args.all):
                continue
            where = f"{v['street'] or '?'} {v['house_no'] or ''}".strip() + f", {v['hood'] or '?'}"
            also = "+" + v["boards"][1]["board"] if len(v["boards"]) > 1 else ""
            m = f"{v['market']['delta_pct']:+d}%" if v["market"] else ""
            print(f"{v['score']:>3} {v['fit']:5} {v['id']:20}{also:8} {v['price'] or '?':>5} {v['rooms'] or '?':>4}r {v['sqm'] or '?':>4}m "
                  f"fl {'?' if v['floor'] is None else v['floor']:>2} {v['area']:7} {m:>5}  {where}  {'; '.join(v['no'] + v['unknown'] + v['warn'])}")
    elif args.cmd == "set":
        set_fields(args.profile, args.ad, people.OWNER, args.status, args.note, args.summary)
        print("נשמר.")
    else:
        global LAN, SHARED
        LAN = bool(getattr(args, "lan", False))
        SHARED = bool(getattr(args, "shared", False))
        threading.Thread(target=queue_worker, daemon=True).start()
        server = ThreadingHTTPServer(("0.0.0.0" if LAN else "127.0.0.1", PORT), Handler)
        print(f"http://127.0.0.1:{PORT}  (Ctrl+C עוצר)")
        if getattr(args, "open", False):
            open_in_chrome(f"http://127.0.0.1:{PORT}")
        if LAN:
            print(f"ברשת הביתית: http://{lan_ip()}:{PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
