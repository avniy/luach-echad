"""The boards, and how each one's ad becomes OUR ad.

Every board has: a search URL built from a profile, a collector script (collectors/<board>.js) that runs inside the
board's own page, and two normalizers (list item, full ad). Everything after this file sees one shape only:

    id "board:native", board, url, seller (private | agent), agency, price (NIS: a month for rent, the asking price
    for sale), rooms, sqm, floor (0 = ground),
    top_floor, type (TYPES), type_raw, city, hood, street, house_no, lat, lon, images, listed_at, updated_at,
    condition (the board's own words: new, renovated, needs work), entrance_flexible,
    features (FEATURES), features_known, on_pillars, description, furniture, entrance, immediate,
    vaad (a month), arnona (a month), board_events [{at, price, kind}], insights [text], park_walk_min, rail
"""
import re
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

TYPES = {"apartment": "דירה", "unit": "יחידת דיור", "garden": "דירת גן", "roof": "גג / פנטהאוז", "studio": "סטודיו",
         "basement": "מרתף / פרטר", "house": "בית פרטי", "duplex": "דופלקס", "parking": "חניה", "storage": "מחסן",
         "land": "מגרש", "other": "אחר"}
NOT_A_HOME = {"parking", "storage", "land"}
# A profile searches one kind of deal. Each board has its own address for each; the ads have the same shape.
DEALS = {"rent": "השכרה", "sale": "קנייה"}


def deal_of(prefs):
    return "sale" if prefs.get("deal") == "sale" else "rent"
FEATURES = {"elevator": "מעלית", "accessible": "נגישה", "mamad": "ממ\"ד", "shelter": "מקלט", "parking": "חניה",
            "balcony": "מרפסת", "ac": "מיזוג", "furnished": "מרוהטת", "renovated": "משופצת", "pets": "חיות מחמד",
            "bars": "סורגים", "storage": "מחסן", "boiler": "דוד שמש"}
BOARDS = {"yad2": "יד2", "madlan": "מדלן", "komo": "קומו", "homeless": "הומלס"}  # in this order: sync order, and who leads a duplicate


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _price(v):
    v = _int(v)
    return v if v and v >= 500 else None  # 0, 1 and 100 are what owners type when they do not want to say


# ---------------- yad2 ----------------

YAD2_TYPES = {"דירה": "apartment", "יחידת דיור": "unit", "דירת גן": "garden", "גג/ פנטהאוז": "roof",
              "גג/פנטהאוז": "roof", "סטודיו/ לופט": "studio", "סטודיו/לופט": "studio", "מרתף/ פרטר": "basement",
              "מרתף/פרטר": "basement", "בית פרטי/ קוטג'": "house", "בית פרטי/קוטג'": "house", "דו משפחתי": "house",
              "דופלקס": "duplex", "טריפלקס": "duplex", "חניה": "parking", "מחסן": "storage", "מגרשים": "land"}
YAD2_MAP_FEATURES = {"elevator": "elevator", "accessibility": "accessible", "shelter": "mamad", "parking": "parking",
                     "balcony": "balcony", "airConditioner": "ac", "furniture": "furnished", "renovated": "renovated",
                     "pets": "pets", "bars": "bars"}
YAD2_DETAIL_FEATURES = {"includeElevator": "elevator", "includeAirconditioner": "ac", "includeSecurityRoom": "mamad",
                        "includeParking": "parking", "includeBalcony": "balcony", "includeBars": "bars",
                        "includeFurniture": "furnished", "isRenovated": "renovated", "isHandicapped": "accessible",
                        "isPetsAllowed": "pets", "includeBuildingShelter": "shelter", "includeFloorShelter": "shelter",
                        "includeBoiler": "boiler", "includeWarehouse": "storage"}


def plain_name(city):
    """yad2 names a few places as two ("מיתר / כרמית"); the other boards and the map know the first name only."""
    return city["name"].split(" / ")[0]


def yad2_url(city, prefs, margin):
    q = {"city": city["code"]}
    if prefs.get("price_max"):
        q["maxPrice"] = int(prefs["price_max"] * margin)
    if prefs.get("price_min"):
        q["minPrice"] = int(prefs["price_min"])
    if prefs.get("rooms_min"):
        q["minRooms"] = max(1, prefs["rooms_min"] - 0.5)
    if prefs.get("rooms_max"):
        q["maxRooms"] = prefs["rooms_max"] + 0.5
    return f"https://www.yad2.co.il/realestate/{'forsale' if deal_of(prefs) == 'sale' else 'rent'}?" + urlencode(q)


def yad2_item(a, tagged):
    """a: the collector's slim list item. tagged: {map feature: set of tokens}, or None when the map did not answer."""
    token = a["token"]
    on_map = bool(a.get("onMap"))
    feats = sorted({YAD2_MAP_FEATURES[f] for f, tokens in (tagged or {}).items() if token in tokens and f in YAD2_MAP_FEATURES})
    return {
        "id": "yad2:" + token, "board": "yad2", "native_id": token,
        "url": "https://www.yad2.co.il/realestate/item/" + token,
        "seller": "private" if a.get("adType") == "private" else "agent", "agency": a.get("agency"),
        "price": _price(a.get("price")), "rooms": _num(a.get("rooms")), "sqm": _int(a.get("sqm")),
        "floor": _int(a.get("floor")), "type": YAD2_TYPES.get((a.get("property") or "").strip(), "other"),
        "type_raw": a.get("property"), "city": a.get("city"), "hood": a.get("hood"), "street": a.get("street"),
        "house_no": a.get("houseNo"), "lat": a.get("lat"), "lon": a.get("lon"), "images": a.get("images") or [],
        "listed_at": a.get("approvedAt"),
        # The list already says when the board shows a struck-out earlier price.
        **({"board_events": [{"at": None, "price": a["priceBefore"], "kind": "before"}]}
           if a.get("priceBefore") and a.get("price") and a["priceBefore"] != a["price"] else {}),
        **({"features": feats, "features_known": True} if tagged is not None and on_map else {}),
    }


def yad2_detail(d):
    add, inp, meta = d.get("additionalDetails") or {}, d.get("inProperty") or {}, d.get("metaData") or {}
    dates = d.get("dates") or {}
    out = {
        "features": sorted({YAD2_DETAIL_FEATURES[k] for k, v in inp.items() if v is True and k in YAD2_DETAIL_FEATURES}),
        "features_known": True,
        "description": meta.get("description"), "furniture": d.get("furnitureInfo"),
        "entrance": add.get("entranceDate"), "immediate": bool(inp.get("isImmediateEntrance")),
        "entrance_flexible": bool(add.get("isEnterDateFlexible")),
        "condition": (add.get("propertyCondition") or {}).get("text"),
        "top_floor": _int(add.get("buildingTopFloor")), "on_pillars": bool(add.get("isPillarBuilding")),
        "vaad": _int(d.get("houseCommittee")),
        "arnona": round(d["propertyTax"] / 2) if isinstance(d.get("propertyTax"), (int, float)) else None,  # yad2 asks per 2 months
        "listed_at": dates.get("createdAt"), "updated_at": dates.get("updatedAt"),
    }
    if d.get("priceBeforeTag") and d.get("price") and d["priceBeforeTag"] != d["price"]:
        out["board_events"] = [{"at": None, "price": d["priceBeforeTag"], "kind": "before"}]
    return out


# ---------------- Madlan ----------------

MADLAN_TYPES = {"flat": "apartment", "gardenapartment": "garden", "penthouse": "roof", "minipenthouse": "roof",
                "roofflat": "roof", "studio": "studio", "duplex": "duplex", "triplex": "duplex", "cottage": "house",
                "privatehouse": "house", "villa": "house", "twofamily": "house", "dualcottage": "house",
                "residentialunit": "unit", "unit": "unit", "basement": "basement", "parking": "parking",
                "storage": "storage"}
MADLAN_AMENITIES = {"elevator": "elevator", "accessible": "accessible", "secureRoom": "mamad", "miklat": "shelter",
                    "airConditioner": "ac", "balcony": "balcony", "grating": "bars", "isFurnished": "furnished",
                    "furnished": "furnished", "unitPetsAllowed": "pets", "storage": "storage", "sunBoiler": "boiler",
                    "garage": "parking"}
MADLAN_EN = {"Limited park access": "מעט פארקים בסביבה"}  # the insights Madlan itself serves in English
MADLAN_IMG ="https://images2.madlan.co.il/t:nonce:v=5;resize:height=640,width=640,fit=outside,withoutEnlargement=true;convert:type=webp/"


# Madlan's own names where they differ from ours, as its published sitemap spells them (read 18.11.2026; the
# file is dated 2022, and these six were not opened on Madlan itself). The other 112 are spelled the same.
MADLAN_CITY = {"טירת כרמל": "טירת הכרמל", "יקנעם עילית": "יוקנעם עילית", "נוף הגליל": "נצרת עילית",
               "כוכב יאיר / צור יגאל": "כוכב יאיר צור יגאל", "עספיא": "עיספיא", "בני עי\"ש": "בני עיש"}


def madlan_city(city):
    return MADLAN_CITY.get(city["name"], plain_name(city))


def madlan_slug(city):
    return madlan_city(city).replace(" ", "-") + "-ישראל"


def madlan_url(city, prefs, margin):
    lo = int(prefs["price_min"]) if prefs.get("price_min") else 0
    hi = int(prefs["price_max"] * margin) if prefs.get("price_max") else ""
    rlo = max(1, prefs["rooms_min"] - 0.5) if prefs.get("rooms_min") else ""
    rhi = prefs["rooms_max"] + 0.5 if prefs.get("rooms_max") else ""
    filters = f"_{lo}-{hi}_{rlo:g}-{rhi:g}" if rlo != "" and rhi != "" else f"_{lo}-{hi}_"
    return f"https://www.madlan.co.il/for-{deal_of(prefs)}/{quote(madlan_slug(city))}?filters={filters}"


def madlan_item(a):
    ad = a.get("addressDetails") or {}
    pt = a.get("locationPoint") or {}
    events = [{"at": e.get("date"), "price": e.get("price"), "kind": e.get("eventType")} for e in a.get("eventsHistory") or []]
    cond = (a.get("generalCondition") or "").lower()
    return {
        "id": "madlan:" + a["id"], "board": "madlan", "native_id": a["id"],
        "url": "https://www.madlan.co.il/listings/" + a["id"],
        "seller": "private" if (a.get("poc") or {}).get("type") == "private" else "agent", "agency": None,
        "price": _price(a.get("price")), "rooms": _num(a.get("beds")), "sqm": _int(a.get("area")),
        "floor": _int(a.get("floor")), "type": MADLAN_TYPES.get((a.get("buildingClass") or "").lower(), "other"),
        "type_raw": a.get("buildingClass"), "city": ad.get("city"), "hood": ad.get("neighbourhood"),
        "street": ad.get("streetName"), "house_no": _int(ad.get("streetNumber")) or ad.get("streetNumber"),
        "lat": pt.get("lat"), "lon": pt.get("lng"),
        "images": [MADLAN_IMG + i["imageUrl"] for i in a.get("images") or [] if i.get("imageUrl")][:12],
        "listed_at": a.get("firstTimeSeen"), "board_events": events,
        "insights": [MADLAN_EN.get(t, t) for t in a.get("insights") or [] if t in MADLAN_EN or re.search("[א-ת]", t)],
        "park_walk_min": _int(a.get("parkWalkTime")),
        "condition_renovated": cond in ("renovated", "new", "asnew"),
    }


def madlan_detail(d):
    am = d.get("amenities") or {}
    feats = {MADLAN_AMENITIES[k] for k, v in am.items() if v is True and k in MADLAN_AMENITIES}
    if _int(d.get("parking")):
        feats.add("parking")
    if d.get("balconyArea"):
        feats.add("balcony")
    if (d.get("generalCondition") or "").lower() in ("renovated", "new", "asnew"):
        feats.add("renovated")
    rail = d.get("closestRailStation") or {}
    return {
        "features": sorted(feats), "features_known": True,
        "description": d.get("description"), "furniture": d.get("furnitureDetails"),
        "entrance": d.get("availableDate"), "immediate": d.get("availabilityType") == "immediate",
        "top_floor": _int(d.get("floors")), "on_pillars": bool(am.get("buildingOnStilts")),
        "vaad": _int(d.get("commonCharges")), "arnona": _int(d.get("monthlyTaxes")),
        "rail": rail.get("name") if isinstance(rail, dict) else None,
        "for_roommates": bool(am.get("forRoommates")),
    }


# ---------------- Komo ----------------
# Komo gives an address but no map pin (app.py's locate() places it), and says who the seller is and what the flat
# has only inside the full ad. Its search filters tell which ads are private and which have an elevator.

KOMO_TYPES = [("מגרש", "land"), ("לופט", "studio"), ("יחידת דיור", "unit"), ("דירת גן", "garden"), ("גג", "roof"), ("פנטהאוז", "roof"), ("סטודיו", "studio"),
              ("דופלקס", "duplex"), ("מרתף", "basement"), ("פרטר", "basement"), ("וילות", "house"), ("בית", "house"),
              ("קוטג", "house"), ("חניה", "parking"), ("מחסן", "storage"), ("דירה", "apartment")]
KOMO_ON = {"mamad": "mamad", "maalit": "elevator", "soragim": "bars", "mizug": "ac", "boiler": "boiler",
           "renovated": "renovated", "gisha": "accessible", "mahsan": "storage", "pets": "pets", "riut": "furnished"}


# Komo writes its own spelling of some names; a name it does not know answers with no ads and no error.
# Checked on 18.11.2026 with one wide rental search per city: every "קרית" is "קריית" there.
KOMO_CITY = {"דאלית אל כרמל": "דלית אל כרמל", "עספיא": "עוספיא"}


def komo_city(city):
    name = plain_name(city)
    return KOMO_CITY.get(name) or re.sub(r"^קרית ", "קריית ", name)


def komo_url(city, prefs, margin):
    q = {"cityName": komo_city(city)}
    if prefs.get("price_min"):
        q["fromPrice"] = int(prefs["price_min"])
    if prefs.get("price_max"):
        q["toPrice"] = int(prefs["price_max"] * margin)
    if prefs.get("rooms_min"):
        q["fromRooms"] = f"{max(1, prefs['rooms_min'] - 0.5):g}"
    if prefs.get("rooms_max"):
        q["toRooms"] = f"{prefs['rooms_max'] + 0.5:g}"
    if prefs.get("private_only"):
        q["privateOnly"] = 1  # Komo shows 20 ads without signing in: spend them on the ones that can fit
    return f"https://www.komo.co.il/code/nadlan/apartments-for-{deal_of(prefs)}.asp?" + urlencode(q)


def komo_item(a, private_search, with_elevator, elevator_complete):
    """a: the collector's list row. private_search: the search asked for private owners only. with_elevator: ids
    the elevator-filtered search returned; elevator_complete: that search was read to its end."""
    parts = [x.strip() for x in (a.get("title") or "").split(",") if x.strip()]
    city = parts[0] if parts else None
    rest = parts[1:]
    street = rest.pop() if rest and (len(rest) == 2 or re.search(r"\d", rest[-1])) else None
    hood = rest[0] if rest else None
    m = re.match(r"^(.*?)\s+(\d+)\S*$", street or "")
    floor = {"קרקע": 0, "מרתף": -1, "פרטר": 0}.get(a.get("floor"), _int(a.get("floor")))
    out = {
        "id": "komo:" + a["id"], "board": "komo", "native_id": a["id"],
        "url": "https://www.komo.co.il/code/nadlan/details/?modaaNum=" + a["id"], "agency": None,
        "price": _price(a.get("price")), "rooms": _num(a.get("rooms")), "sqm": _int(a.get("sqm")), "floor": floor,
        "top_floor": _int(a.get("topFloor")),
        "type": next((t for word, t in KOMO_TYPES if word in (a.get("type") or "")), "other"), "type_raw": a.get("type"),
        "city": city, "hood": hood, "street": m.group(1) if m else street, "house_no": _int(m.group(2)) if m else None,
        "images": [a["image"]] if a.get("image") else None,
    }
    if private_search:
        out["seller"] = "private"  # otherwise the full ad says who the seller is
    if a["id"] in with_elevator:
        out["features"], out["elevator_known"] = ["elevator"], True
    elif elevator_complete:
        out["elevator_known"] = True
    return out


AGO = {"דקה": 60, "דקות": 60, "שעה": 3600, "שעות": 3600, "שעתיים": 7200, "יום": 86400, "ימים": 86400, "יומיים": 172800,
       "שבוע": 604800, "שבועות": 604800, "שבועיים": 1209600, "חודש": 2592000, "חודשים": 2592000, "חודשיים": 5184000}


def _ago(text):
    """Komo writes "updated 3 hours ago": the time that was, or None. From a day up, the date only."""
    m = re.search(r"לפני:?\s*(\d+)?\s*(" + "|".join(sorted(AGO, key=len, reverse=True)) + ")", text or "")
    if not m:
        return None
    secs = int(m.group(1) or 1) * AGO[m.group(2)]
    at = datetime.now() - timedelta(seconds=secs)
    return at.isoformat(timespec="seconds") if secs < 86400 else at.strftime("%Y-%m-%dT00:00:00")


def komo_detail(d):
    feats = {KOMO_ON[c] for c in d.get("on") or [] if c in KOMO_ON}
    if _int(d.get("parking")):
        feats.add("parking")
    if _int(d.get("balconies")):
        feats.add("balcony")
    if re.search("משופץ|חדש", d.get("condition") or ""):
        feats.add("renovated")
    ent = re.match(r"(\d{2})/(\d{2})/(\d{4})", d.get("entrance") or "")
    out = {
        "features": sorted(feats), "features_known": True, "elevator_known": True,
        "seller": "private" if "פרטי" in (d.get("seller") or "") else "agent",
        "description": d.get("description"), "furniture": d.get("furniture"), "condition": d.get("condition"),
        "updated_at": _ago(d.get("updated")),
        "entrance": f"{ent.group(3)}-{ent.group(2)}-{ent.group(1)}T00:00:00" if ent else None,
        "immediate": "מיידי" in (d.get("entrance") or ""),
        "top_floor": _int(re.sub(r"\D", "", d.get("floors") or "") or None),
        "vaad": _int(re.sub(r"\D", "", d.get("vaad") or "") or None),
        "for_roommates": "shutafim" in (d.get("on") or []),
    }
    tax = _int(re.sub(r"\D", "", d.get("arnona") or "") or None)
    out["arnona"] = round(tax / 2) if tax else None  # Komo, like yad2, asks owners for the two-month bill
    if d.get("images"):
        out["images"] = d["images"]
    return out


# ---------------- Homeless ----------------
# Its "rent" board is the owners' board (agents have their own section), it gives a street without a house number
# and no pin, and its room filter takes the position in its own list (1 room = 1, 1.5 = 2, 2 = 3 ...).

# Homeless: the names as its own city list spells them (asked 18.11.2026), where they differ from ours.
HOMELESS_CITY = {"תל אביב יפו": "תל אביב", "אפרת": "אפרתה", "מעלות תרשיחא": "מעלות-תרשיחא", "בנימינה גבעת עדה": "בנימינה"}
HOMELESS_ON = {"furnished": "furnished", "Elevators": "elevator", "Airconditioner": "ac", "parking": "parking",
               "Terrace": "balcony", "bars": "bars", "safeRoom": "mamad", "Storage": "storage", "Renovated": "renovated",
               "WaterHeater": "boiler", "pets": "pets"}


def _il_date(s):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}T00:00:00" if m else None


def homeless_url(city, prefs, margin):
    parts = ["city=" + quote(HOMELESS_CITY.get(city["name"], plain_name(city)))]
    if prefs.get("price_min"):
        parts.append(f"flong3={int(prefs['price_min'])}")
    if prefs.get("price_max"):
        parts.append(f"flong3_1={int(prefs['price_max'] * margin)}")
    if prefs.get("rooms_min"):
        parts.append(f"inumber4={int((max(1, prefs['rooms_min'] - 0.5) - 1) * 2 + 1)}")
    if prefs.get("rooms_max"):
        parts.append(f"inumber4_1={int((prefs['rooms_max'] + 0.5 - 1) * 2 + 1)}")
    return f"https://www.homeless.co.il/{deal_of(prefs)}/" + "$$".join(parts)


def homeless_item(a, deal="rent"):
    m = re.match(r"^(.*?)\s+(\d+)\S*$", a.get("street") or "")  # the sale board often writes the house number too
    return {
        "id": "homeless:" + a["id"], "board": "homeless", "native_id": a["id"],
        "url": f"https://www.homeless.co.il/{deal}/viewad,{a['id']}.aspx", "seller": "private", "agency": None,
        "price": _price(a.get("price")), "rooms": _num(a.get("rooms")),
        "floor": {"קרקע": 0, "מרתף": -1}.get(a.get("floor"), _int(a.get("floor"))),
        "type": next((t for word, t in KOMO_TYPES if word in (a.get("type") or "")), "other"), "type_raw": a.get("type"),
        "city": a.get("city"), "hood": a.get("hood") or None, "street": (m.group(1) if m else a.get("street")) or None,
        "house_no": _int(m.group(2)) if m else None,
        "images": [a["image"]] if a.get("image") else None,
        "entrance": _il_date(a.get("entrance")), "immediate": a.get("entrance") == "מיידי" or None,
        "updated_at": _il_date(a.get("updated")),
    }


def homeless_detail(d):
    out = {"description": d.get("description"), "sqm": _int(d.get("sqm")),
           "for_roommates": "room-mates" in (d.get("on") or [])}
    if d.get("known"):
        out.update(features=sorted({HOMELESS_ON[c] for c in d["on"] if c in HOMELESS_ON}), features_known=True, elevator_known=True)
    top = re.search(r"מתוך\s*(\d+)", d.get("floor") or "")
    out["top_floor"] = _int(top.group(1)) if top else None
    tax = _int(re.sub(r"\D", "", d.get("arnona2m") or "") or None)
    out["arnona"] = round(tax / 2) if tax else None
    if d.get("images"):
        out["images"] = d["images"]
    return out


# ---------------- what the owner's text says ----------------

BILLS = {"ארנונה": "arnona", "מים": "water", "חשמל": "electricity", "ועד": "vaad", "אינטרנט": "internet", "גז": "gas"}
BILLS_HE = {"arnona": "ארנונה", "water": "מים", "electricity": "חשמל", "vaad": "ועד בית", "internet": "אינטרנט", "gas": "גז"}


# ---------------- an ad the person pasted in ----------------
# Text from anywhere: a Facebook or WhatsApp post, a board we do not read, a friend's message. Nothing is fetched:
# the person brings the text (and, if they like, the link they took it from) and it becomes one more ad on the board.
OTHER = {"paste": "הודבקה"}
HE = "֐-׿"
NUM_WORDS = {"חדר": 1, "שני": 2, "שניים": 2, "שתי": 2, "שלושה": 3, "שלוש": 3, "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5, "שישה": 6, "שש": 6}
FLOOR_WORDS = {"קרקע": 0, "ראשונה": 1, "שנייה": 2, "שניה": 2, "שלישית": 3, "רביעית": 4, "חמישית": 5, "שישית": 6,
               "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6}
PASTE_FEATURES = {"elevator": "מעלית", "mamad": r"ממ[\"״']?ד", "shelter": "מקלט", "parking": "חניה|חנייה", "balcony": "מרפסת",
                  "ac": "מזגן|מזגנים|מיזוג", "furnished": "מרוהטת|ריהוט מלא|מרוהט", "renovated": "משופצת|שופצה|משופץ",
                  "pets": "חיות מחמד|בעלי חיים", "bars": "סורגים", "storage": "מחסן", "boiler": "דוד שמש", "accessible": "נגישה|נגיש לנכים"}
PHONE = re.compile(r"(?:\+?972[\s-]?|0)(?:[23489]|5\d|7\d)[\s-]?\d{3}[\s-]?\d{4}|\[hidden information\]")


def phone_of(s):
    """An Israeli phone number as written in an ad, in the shape 052-1234567 (None when it is not one)."""
    d = re.sub(r"\D", "", s)
    if d.startswith("972"):
        d = "0" + d[3:]
    if not re.fullmatch(r"0\d{8,9}", d):
        return None
    return f"{d[:3]}-{d[3:]}" if len(d) == 10 else f"{d[:2]}-{d[2:]}"


def pasted_item(text, url, city_name, hoods, deal="rent"):
    """Our ad from free text. Only what the text says is filled in. The person pasted it to call about the flat, so
    its phone numbers stay (`phones`): only in an ad a person pastes, never from a board.
    Returns (ad, missing): missing names the basics the text did not give."""
    import hashlib
    text = re.sub(r"[ \t ‎‏]+", " ", str(text or "")).strip()[:6000]
    flat = PHONE.sub(" ", text).replace("\n", " ")   # read without the phone numbers: a number is never a price
    out = {"board": "paste", "seller": None, "agency": None, "city": city_name, "description": text, "images": None}
    out["phones"] = list(dict.fromkeys(n for n in (phone_of(m.group(0)) for m in PHONE.finditer(text)) if n))[:3]
    out["native_id"] = hashlib.sha1(re.sub(r"\W+", "", flat).encode()).hexdigest()[:12]
    out["id"] = "paste:" + out["native_id"]
    out["url"] = url if re.match(r"https?://[^\s\"'<>]{4,600}$", url or "") else None

    money = r"(\d{1,3}(?:[,.]\d{3})+|\d{3,8})"
    m = re.search(r"(\d(?:[.,]\d{1,3})?)\s*(?:מיליון|מליון|מ')(?![" + HE + "])", flat) if deal == "sale" else None
    if m:
        out["price"] = int(float(m.group(1).replace(",", ".")) * 1_000_000)
    else:
        found = (re.findall(money + r"\s*(?:₪|ש[\"״']?ח|שקל|nis|ils)", flat, re.I) + re.findall(r"(?:₪|ILS|NIS)\s*" + money, flat, re.I)
                 + re.findall(r"(?:מחיר|שכירות|שכ\"ד|שכר דירה|price)\s*:?\s*" + money, flat, re.I))
        prices = [p for p in (_price(x.replace(",", "").replace(".", "")) for x in found) if p]
        out["price"] = prices[0] if prices else None

    m = re.search(r"(\d(?:[.,]5)?)\s*(?:חד(?:רים|ר|')?(?![" + HE + r"])|rooms?)", flat, re.I)
    words = re.search(r"(" + "|".join(NUM_WORDS) + r")\s+(?:וחצי\s+)?חדרים(\s+וחצי)?", flat)
    beds = re.search(r"(\d)\s*(?:beds?|bedrooms?|חדרי שינה)", flat, re.I)
    if m:
        out["rooms"] = _num(m.group(1).replace(",", "."))
        if re.match(r"\s*(?:חד(?:רים|ר|')?)\s+וחצי", flat[m.start(0) + len(m.group(1)):]):
            out["rooms"] += 0.5
    elif words:
        out["rooms"] = NUM_WORDS[words.group(1)] + (0.5 if "וחצי" in words.group(0) else 0)
    elif re.search(r"חדר וחצי", flat):
        out["rooms"] = 1.5
    elif beds:
        out["rooms"] = int(beds.group(1)) + 1  # bedrooms, plus the living room
    elif re.search(r"סטודיו|studio", flat, re.I):
        out["rooms"] = 1
    else:
        out["rooms"] = None

    m = re.search(r"(\d{2,3})\s*(?:מ[\"״']?ר|מטר(?:ים)?(?: רבוע)?|sqm|m2|מ²)(?![" + HE + "])", flat, re.I)
    out["sqm"] = int(m.group(1)) if m else None

    m = re.search(r"קומ[הת]\s*:?\s*(-?\d{1,2}|" + "|".join(sorted(FLOOR_WORDS, key=len, reverse=True)) + r")['׳]?(?![" + HE + r"])"
                  r"(?:\s*(?:מתוך|מ-|/)\s*(\d{1,2}))?", flat)
    out["floor"] = None if not m else FLOOR_WORDS[m.group(1)] if m.group(1) in FLOOR_WORDS else int(m.group(1))
    out["top_floor"] = int(m.group(2)) if m and m.group(2) else None

    lead, name = r"(?:ב?רחוב|ב?רח['׳]|ב?שד(?:רות|['׳]))\s+", "([" + HE + r"\"'׳ -]{2,28}?)"
    stop = r"(?:קומה|קומת|ליד|פינת|דירה|דירת|להשכרה|למכירה|קרוב|מול|כניסה|במחיר|מחיר|ב[" + HE + r"]{3,})"
    m = (re.search(lead + name + r"\s+(\d{1,3})(?!\d)", flat)  # a name of several words ends at its house number
         or re.search(lead + name + r"(?=\s*(?:[,.!?:;)(]|$)|\s+" + stop + r"(?![" + HE + "]))", flat))
    out["street"] = m.group(1).strip(" -") if m else None
    out["house_no"] = _int(m.group(2)) if m and m.lastindex == 2 else None
    out["hood"] = next((h for h in sorted(hoods, key=len, reverse=True) if len(h) > 3 and h in flat), None)

    out["type"] = next((t for word, t in KOMO_TYPES if word in flat and t not in NOT_A_HOME), "apartment")
    out["type_raw"] = TYPES[out["type"]]
    no = r"(?:ללא|בלי|אין|לא כולל)\s+(?:[" + HE + r"]+\s+ו?)?"
    out["features"] = sorted(f for f, pat in PASTE_FEATURES.items()
                             if re.search(r"(?:" + pat + ")", flat) and not re.search(no + r"(?:" + pat + ")", flat))
    out["features_known"] = False  # a text says what it has, never the whole list
    if re.search(r"ללא תיווך|בלי תיווך|לא למתווכים|ללא מתווכים|ישירות מבעל|מבעלים|no agent", flat, re.I):
        out["seller"] = "private"
    elif re.search(r"דמי תיווך|בתיווך|מתווך|משרד תיווך|נדל[\"״]?ן בע|רי/?מקס|אנגלו סכסון|בלעדיות", flat):
        out["seller"] = "agent"
    out["immediate"] = True if re.search(r"כניסה מי[י]?דית|פנויה עכשיו|זמינה מי[י]?ד", flat) else None
    m = re.search(r"(?:כניסה|פינוי|מתפנה|available)\s*(?:ב-?|:|מה-?|from)?\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", flat, re.I)
    if m:
        year = int(m.group(3) or datetime.now().year)
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            out["entrance"] = f"{year + 2000 if year < 100 else year}-{month:02d}-{day:02d}T00:00:00"
    missing = [he for key, he in (("price", "מחיר"), ("rooms", "חדרים"), ("street", "רחוב"), ("floor", "קומה"), ("sqm", "גודל"))
               if out.get(key) is None]
    return out, missing


def read_text(ad):
    """Things owners write in the text that the board's own fields get wrong or do not have."""
    text = " ".join(filter(None, [ad.get("description"), ad.get("furniture")]))
    flags, included, excluded = [], set(), set()
    if not text and not ad.get("condition"):
        return {"flags": flags, "included": [], "excluded": []}
    if re.search(r"מחפש\S* שות|שותף או שותפה|משותפ\S* לכל|מטבח\S* (ענק\S* )?(מאובזר )?ו?משותפ|והמטבח משותפים|לאישה בלבד|לבחורה בלבד", text):
        flags.append("roommates")
    if re.search(r"שומרי שבת|שומרי תורה|חרדי|חרדלי|לדתיים|יחיד דתי|זוג דתי|מסורתיים/דתיים|כשרות", text):
        flags.append("religious")
    if ad.get("type") == "basement" or (re.search(r"מרתף|תת.?קרקעי|חצר אנגלית", text) and not re.search(r"(לא|אינה|שאינה|אינו) ב?מרתף", text)):
        flags.append("basement")
    # What matters to a buyer and no board has a field for.
    if re.search(r"(?<!לא )(?<!ללא )(דמי מפתח|דמ\"פ|דיירות מוגנת|דייר מוגן)", text):
        flags.append("key_money")
    if re.search(r"תמ\"?א\s?38|תמ״א|פינוי[ -]?בינוי|התחדשות עירונית", text):
        flags.append("renewal")
    if re.search(r"דירה מושכרת|מושכרת (ב|ל|עד)|מושכר (ב|ל|עד)|שוכר(ים)? קיימ|תשואה", text):
        flags.append("rented")
    cond = ad.get("condition") or ""
    if "מקבלן" in cond or re.search(r"ישירות מה?קבלן|חדשה? מקבלן|על הנייר|דירות אחרונות|הון עצמי החל|מחיר למשתכן", text):
        flags.append("new_build")
    if re.search(r"דרוש\S* שיפוץ|זקוק\S* לשיפוץ", cond + " " + text):
        flags.append("needs_work")
    m = re.search(r"(\d+)\s*מדרגות|(שני|שתי|שלוש\S*|כמה|מספר|מס') (גרמי )?מדרגות|חצי קומה", text)
    if m:
        flags.append("stairs")
    for part in re.split(r"[\n.!]|(?<=\S) - ", text):
        if "כולל" not in part:
            continue
        neg = re.search(r"(לא|אינו|ללא) כולל", part)
        if neg and "כולל" in part[:neg.start()]:  # "כולל ארנונה ומים. לא כולל חשמל" written as one sentence
            for word, key in BILLS.items():
                (included if word in part[:neg.start()] else excluded if word in part[neg.start():] else set()).add(key)
            continue
        for word, key in BILLS.items():
            if word in part:
                (excluded if neg else included).add(key)
    if re.search(r"כולל (את )?כל החשבונות|כולל הכל|כולל הכול", text):
        included |= {"arnona", "water", "vaad"} - excluded
    return {"flags": flags, "stairs_text": m.group(0) if m else None,
            "included": sorted(included - excluded), "excluded": sorted(excluded)}
