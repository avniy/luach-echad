# 🤖 For an AI agent working with this app

"לוח אחד" is a local app that reads four Israeli rental boards (yad2, Madlan, Komo, Homeless) through the user's own
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

`prefs` (what the questionnaire asks):

```json
{
  "who": "one sentence about who will live there (optional)",
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

`access.need` = no stairs: an elevator, or a floor up to `max_floor`. Feature keys are in `meta.features`.

## 🗂️ Where things are

- `app.py`: profiles, the pull, fit / score / market comparison / duplicates (worked out when read, never stored),
  the local server.
- `boards.py`: per board, the search address, and the two normalizers into the one ad shape described at its top.
- `extension/`: the Chrome extension; `extension/collectors/<board>.js` read the board's page.
- `ui/index.html`: the whole interface.
- `data/`: the person's searches, ads, people and settings. Not part of the repository.

Known limits (which boards give how much, where locations are approximate) are listed in `README.md`: say them when
you report results, rather than presenting a partial read as complete.
