**English** · [עברית](README.md)

# 🏠 לוח אחד (Luach Echad, "one board")

All the Israeli apartment rental boards in one place, on your own computer.

The app reads your search on yad2, Madlan, Komo and Homeless, merges the ads into one shape, recognises the same flat
when it appears on several boards, and ranks everything by what matters to you: area, budget, rooms, no brokers, no
stairs and more. You get a list, a map, a comparison with market prices, what is within walking distance, and what
changed in each ad since last time.

Everything runs on your machine: no server, no sign-up, and your data stays in one folder on your computer.
The interface is in Hebrew.

## 🧰 What you need

| | |
|---|---|
| Computer | Windows 10 or 11. macOS and Linux should work with `start.sh`, but were not tested |
| Browser | Google Chrome (version 116 or newer) |
| Python | 3.10 or newer (tested with 3.12). No extra packages |
| Internet | An ordinary home connection |
| Setup time | About ten minutes, once |

## ⚙️ Install

**1. Python.** Download it from [python.org/downloads](https://www.python.org/downloads/) and install. On the
installer's first screen tick **Add python.exe to PATH**.

**2. The app.** On this GitHub page: **Code → Download ZIP**. Extract it to a permanent folder, for example
`C:\luach-echad`. Do not leave it in Downloads: the extension is loaded from this folder, and stops working if the
folder moves.

**3. The Chrome extension.** It is what reads the boards for you.

1. Open `chrome://extensions` in Chrome
2. Switch on **Developer mode** (top right)
3. Click **Load unpacked**
4. Choose the `extension` folder inside the app's folder

"לוח אחד: קורא הלוחות" now appears in your list of extensions. Chrome may remind you now and then that an extension
is running in developer mode: that is expected.

**4. Start it.** Double-click `start.cmd`. A black window opens (do not close it: it is the app), and the app's own
window opens at `http://127.0.0.1:7461`.

## 🚀 Using it

1. **A new profile.** Click "+ פרופיל חדש" and answer the questionnaire: city, neighbourhoods, budget, rooms, what is
   a must and what is a plus. A profile is one person's search. You can have several.
2. **Sync ("סנכרון").** The app opens a background tab in Chrome for each board (up to four), reads the boards side by
   side, each at the pace of an ordinary visitor, and closes the tabs about two minutes after it finishes. A few
   minutes in all. Chrome has to stay open, and you can keep working in it meanwhile.
3. **The board.** Ads that fit come first, with a score and the reasons. Clicking an ad opens photos, a map, what is
   around, which boards it came from, and a link to the original ad on its board.
4. **Mark ads.** Favourite, contacted, visit, not relevant, and a free note.
5. **"Read the full ad".** The list gives only the basics. The button loads one ad's page and brings its full text
   and features.
6. **Search together.** `start-lan.cmd` instead of `start.cmd` also opens the app to devices on your home network.
   With the "שיתוף" (share) button you make an invite link for a partner: they see the search, mark ads and write
   notes. Without a link nobody sees anything.

Contacting the owner is something you do yourself, on the board.

## ⚠️ Limits worth knowing

**How ads are pulled**

- **Only when you ask.** Nothing is pulled automatically. A sync happens when you click, with Chrome open and the
  extension installed.
- **Slow on purpose.** The boards are read side by side, but each board gets one request at a time, with pauses.
  Once or twice a day is enough. Frequent syncs will make the boards block your browser.
- **Boards change their sites.** When one does, reading that board breaks until the code is updated.

**Board by board**

| Board | What to know |
|---|---|
| yad2 | The fullest board. For some ads the map pin is off by a few hundred metres (that is how yad2 gives it) |
| Madlan | Sometimes shows a "press and hold" check. The app does not try to pass it, and nobody will do it for you: open Madlan, press and hold, then click "פתרתי" ("solved") in the app. Pulled at most once every 6 hours, and up to 5 full ads each time |
| Komo | Shows only the first 20 ads unless you are signed in. If you sign in to Komo in Chrome (yourself), the app reads all the pages. No map pin: the location comes from the address |
| Homeless | Only the first results page is read. No house number, so an ad is placed at the middle of its street |

**What the app covers**

- **Rent only.**
- **118 cities and towns:** every large city and most towns that have rentals on yad2. The full list is in the
  questionnaire, where you pick the city. A town with no rental ads on yad2 right now is not included.
  Tested in depth only in Petah Tikva and Ramat Gan. Most towns were checked on yad2 only: Komo, Homeless and
  Madlan may miss ads there.
- **Duplicate matching can be wrong.** The same street, floor and price with no house number count as the same
  flat. On a long street that can merge two different flats. Inside an ad you see its sources separately.
- **Walking minutes are an estimate** (straight line times 1.3), not a real route.
- **Street View** is shown as a link. To see it inside the app you need a key of your own (see below).

**Security**

- **Home network only.** The app speaks plain HTTP and has no passwords, only invite links. Do not open it to the
  internet, neither by port forwarding nor through a tunnelling service.

## 🔒 Privacy

- **Your data stays with you:** searches, ads, marks and notes are kept in the `data` folder inside the app's
  folder. There is no server of ours and no tracking.
- **Not stored:** owners' names and phone numbers. The app only reads: it sends no messages and contacts nobody.
- **Where the app does connect:** the boards themselves (through your Chrome, like ordinary browsing); OpenStreetMap
  for map tiles, for finding addresses (an ad's street and city are sent) and for places around (the city's bounds
  are sent); Google Fonts and unpkg for a font and the map library; and Google Maps only when you open Street View.

## 🧩 What the extension may do

The extension was built only for this app:

- **Access to four sites only:** `yad2.co.il`, `madlan.co.il`, `komo.co.il`, `homeless.co.il`, and the app itself at
  `127.0.0.1:7461`. It cannot see or touch any other site or tab.
- **Three actions only:** open a page of one of the boards in a background tab of its own (one per board), read the
  ads from it, and show a notification.
- **It does not:** type, click, sign in to accounts, send anything to the boards, or try to pass "I am not a robot"
  checks.
- All its code is in the `extension` folder, a few hundred lines. You can read it.

## 🛠️ Common problems

| What you see | What to do |
|---|---|
| "חסר התוסף של לוח אחד בכרום הזה" (the extension is missing) | Step 3 of the install. Then refresh the page |
| "התוסף לא מחובר" (not connected) during a sync | Make sure the app is open in Chrome (not another browser) and the extension is enabled in `chrome://extensions` |
| A board marked "מבקש אימות אנושי" (asks for a human check) | Open the board in Chrome, pass the check yourself, click "פתרתי" and sync again |
| Komo: "בלי התחברות רק 20 מודעות" (only 20 ads) | Sign in to Komo in Chrome, or settle for 20 |
| `Python was not found` | Install Python and tick Add to PATH (step 1) |
| The page does not open | Check that the black window is open, and open `http://127.0.0.1:7461` in Chrome |
| Port 7461 is taken | Another program is using it. Close it, or an earlier copy of the app |
| I moved the folder and the extension disappeared | In `chrome://extensions` remove it and load it again from the new place |

## 🗺️ Optional: Street View inside the app

Without a key you get a link that opens in Google Maps. To embed the view in the ad:

1. In Google Cloud Console create an API key and enable only the **Maps Embed API** (free).
2. Restrict the key to the address `http://127.0.0.1:7461/*` and to the Maps Embed API only.
3. Save it as a single line in the file `data/maps-key.txt`.

## 🔄 Updating and removing

- **Update:** download again and replace the files (the `data` folder stays), then click the extension's reload
  arrow in `chrome://extensions`.
- **Remove:** remove the extension in `chrome://extensions` and delete the folder. That is all: nothing was
  installed anywhere else.

## 🤝 Fair use

The tool is meant for a personal apartment search. It reads what you would see yourself while browsing, at a
person's pace, and sends you to the original ad on its board. Each board has its own terms of use, and keeping to
them is the responsibility of whoever uses the tool. Do not use it to collect ads in bulk, to pass them on, or to
get around blocks.

## 🤖 For an AI agent

Have an AI agent that works on your computer? Give it this page's address and it can download, install and start
the app for you. Only the Chrome extension has to be loaded by you (step 3). `AGENTS.md` tells it how to install,
the shell commands, the local interface and the rules it has to keep.

## 🍪 Enjoyed the app?

The app is free and stays free. Enjoyed it? **[Buy me a treat](https://treat.dogware.ai/)**.
