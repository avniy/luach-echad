# 🤖 For an AI agent working with this app

"לוח אחד" is a local app that reads four Israeli apartment boards (yad2, Madlan, Komo, Homeless), for rent or for
sale, through the user's own
Chrome, merges the ads into one shape and ranks them against a profile. If the person you work for runs it on this
computer, you can read the results, mark ads and start a pull for them. Setup is in `README.md`.

## 📏 Rules: keep them

- **Read only.** Never contact an owner, never send anything to a board, and do not collect owners' names or phone
  numbers. Contacting an owner is the person's own step, on the board itself.
- **Never try to pass a board's human check** ("press and hold", captcha) or its sign-in. Tell the person: only they
  can. After they passed Madlan's check, they press "פתרתי" in the app (or you `POST /api/boards/madlan/retry`
  when they tell you it is done).
- **Pull rarely.** Once or twice a day per profile. The pace inside a pull is slow on purpose: do not shorten the
  pauses in `app.py` and do not raise the per-board limits.
- **Home use.** The app has no passwords and speaks plain HTTP. Never expose port 7461 to the internet.
- **Personal data stays local.** Everything is in `data/`. Do not upload it anywhere.

## ▶️ What has to be running

The person starts the app (`start.cmd`, or `python app.py serve`) and keeps it open in Chrome with the extension
from `extension/` installed. The extension is the only thing that reads the boards; without Chrome open, a pull
answers "התוסף של לוח אחד לא מחובר".

## 🧰 Installing it for the person

If the person gave you the repository's address and asked you to set it up, you can do all of it but one step:

1. **Python 3.10 or newer.** Check `python --version`. If it is missing, tell the person to install it from
   python.org with "Add python.exe to PATH" ticked (or install it yourself only if they agree).
2. **The code, in a permanent folder** (not Downloads; the extension is loaded from it):
   `git clone <the repository's address>`, or the ZIP from the repository page (Code → Download ZIP).
3. **The Chrome extension: the person does this, you cannot.** Chrome's extensions page cannot be driven by a
   script. Give them the four clicks and the exact folder: `chrome://extensions` → Developer mode → Load unpacked →
   `<the folder>\extension`.
4. **Start it:** `start.cmd`, or `python app.py serve --open`. Leave it running.
5. **Check:** `GET http://127.0.0.1:7461/api/me` says `"browser": true` once the app's page is open in Chrome with
   the extension loaded. Until then a pull answers that the extension is not connected.
6. **The first search:** ask the person what they look for (city, neighbourhoods, budget, rooms, must-haves), then
   `POST profiles` with `prefs` as below and `POST profiles/<id>/sync`. Or let them answer the questionnaire in the
   app.

Nothing else is installed: no packages, no service, no account.

## ⌨️ From a shell

```
python app.py list <profile>                 the ads that fit, best first (add --all for the ones that do not)
python app.py sync <profile> [board]         pull now through the running app; board = yad2 | madlan | komo | homeless
python app.py set <profile> <ad id> [--status S] [--note "..."] [--summary "..."]
```

- Profiles are `p1`, `p2`, ... (`data/profiles/<id>.json`). An ad id looks like `yad2:abc123`.
- `--status`: `shortlist`, `contacted`, `visit`, `rejected`, or `""` to clear.
- `--summary` is yours: a short text about the ad after you read it, in the person's language. It is shown in the
  ad's view. `--note` is the person's own note; write there only what they tell you to.
- A `list` line: score, fit (`yes` / `maybe` / `no`), ad id, a second board that lists the same flat, price, rooms,
  size, floor, area (`in` the chosen neighbourhoods / `near` / `out`), price against similar flats, address, and
  the reasons.

## 🌐 Over HTTP, on this computer

`http://127.0.0.1:7461/api/...`, JSON. A request from this computer is the owner. Send `Content-Type:
application/json` on every POST, and no `Origin` header.

| Request | What it does |
|---|---|
| `GET meta` | cities with their neighbourhoods, feature names, board names |
| `GET me` | `browser: true` when the extension is connected and a pull can run |
| `GET profiles` | the profiles with their counts |
| `POST profiles` `{name, prefs}` | a new profile; answers `{id}` |
| `GET profiles/<id>` | the profile, every ad already merged across boards, scored and explained, and each board's state |
| `POST profiles/<id>/prefs` `{name, prefs}` | change the search |
| `POST profiles/<id>/sync` `{board?}` | start a pull; follow it with `GET sync` (`running`, `steps`, `error`) |
| `POST profiles/<id>/ads/<ad id>/detail` | read one ad's full page now (one page view) |
| `POST profiles/<id>/ads/<ad id>` `{status?, note?}` | mark an ad (a summary is set from the shell: `set ... --summary`) |
| `POST profiles/<id>/paste` `{text, url?}` | add an ad the person saw elsewhere, from its text (nothing is fetched; phone numbers are removed); answers `{id, known, missing}` |
| `POST profiles/<id>/ads/<ad id>/remove` | remove a pasted ad (ids that start with `paste:` only) |

`prefs` (what the questionnaire asks):

```json
{
  "who": "one sentence about who will live there (optional)",
  "deal": "rent",
  "city": "פתח תקווה",
  "hoods": ["names from meta.cities[].hoods; empty = the whole city"],
  "radius_km": 1.2,
  "price_max": 5000, "price_min": null,
  "rooms_min": 1, "rooms_max": 2.5,
  "sqm_min": null,
  "private_only": true,
  "access": {"need": true, "max_floor": 1},
  "features": {"parking": "nice", "mamad": "must"},
  "hide": ["roommates", "religious", "basement"]
}
```

`deal` is `rent` (the default) or `sale`. It is set when the profile is made and never changes: open another profile
for the other kind. Prices are per month for rent and the asking price for sale. For sale, `market` compares the
price per square metre (`market.per` is `sqm`, `market.km` the radius used), each ad has `per_sqm`, and `flags` may
hold `key_money`, `odd_price`, `new_build`, `needs_work`, `renewal` or `rented` (read from the ad, so not certain).
A purchase search needs extension 1.1 or newer; the app says so when it meets an older one.

`access.need` = no stairs: an elevator, or a floor up to `max_floor`. Feature keys are in `meta.features`.

## 🗂️ Where things are

- `app.py`: profiles, the pull, fit / score / market comparison / duplicates (worked out when read, never stored),
  the local server.
- `boards.py`: per board, the search address, and the two normalizers into the one ad shape described at its top.
- `extension/`: the Chrome extension; `extension/collectors/<board>.js` read the board's page.
- `ui/index.html`: the whole interface. Its texts are Hebrew in the code; `ui/lang/<code>.json` holds one
  translation each (`en.json` today), and a text without a line there simply shows in Hebrew.
- `data/`: the person's searches, ads, people and settings. Not part of the repository.

What a pull changed is not stored apart: every ad carries `first_seen`, `gone_since` and `changes` (each with the
pull's time), and `meta.syncs` lists the pulls with what each board gave. An ad is marked gone only when its
board's list was read to the end (`complete`).

Known limits (which boards give how much, where locations are approximate) are listed in `README.md`: say them when
you report results, rather than presenting a partial read as complete.
