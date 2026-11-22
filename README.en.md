**English** · [עברית](README.md)

# 🏠 לוח אחד (Luach Echad, "one board")

All the Israeli apartment boards, for rent and for sale, in one place, on your own computer.

The app reads your search on yad2, Madlan, Komo and Homeless, merges the ads into one shape, recognises the same flat
when it appears on several boards, and ranks everything by what matters to you: area, budget, rooms, no brokers, no
stairs and more. You get a list, a map, a comparison with market prices, what is within walking distance, and what
changed in each ad since last time.

Everything runs on your machine: no server, no sign-up, and your data stays in one folder on your computer.
The interface is in Hebrew.

## ⚖️ Terms of use, in short

If you download and use it, these are the terms:

- **Private, non-commercial use** (the licence below). Brokers and businesses: write to me.
- **The boards belong to their owners.** Each board has its own terms, and keeping to them is your responsibility.
  The app reads, in your own browser and slowly, what you would see yourself, and stops when a board asks for a
  human check. Do not try to get around a block, collect at scale, or pass ads on.
- **No warranty on the data.** Prices, fit, score, the market comparison, "the same flat on several boards",
  walking minutes, places around and English names are worked out automatically and can be wrong. What counts is
  the original ad on the board, and what the owner tells you.
- **A buyer's numbers are an estimate, not advice.** Purchase tax by the Tax Authority's table (with the date it is
  known to hold until), and a monthly payment at the average interest the Bank of Israel publishes. They can get
  old: "System status" at the bottom of the screen shows when each was last updated. Before deciding: a mortgage
  advisor, a lawyer and an appraiser.
- **Contacting the owner** is something you do yourself, on the board. The app sends no messages and keeps no phone
  numbers from the boards.
- **What runs by itself:** the automatic check (only if you switched it on, and only while the app and the browser
  are open), a check for a new version twice a day, and an update that downloads files from GitHub only after your
  click, with a backup.
- **Outside services** the app connects to are listed under "Privacy".
- **Home network mode** (`start-lan.cmd`) is for the home network only: no password, no encryption. Never expose it
  to the internet.
- **AS IS:** the software comes as is, without any warranty, as far as the law allows (the licence's "No
  Liability" section).

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

The interface opens in Hebrew. The "English" link at the bottom of every screen switches it to English; what the
boards wrote (streets, neighbourhoods, the ad's text) stays in Hebrew. The Hebrew labels below are the ones you
see before switching.

1. **A new profile.** Click "+ פרופיל חדש" and answer the questionnaire: rent or buy, city, neighbourhoods, budget,
   rooms, what is a must and what is a plus. A profile is one search of one person, to rent or to buy. You can
   have several.
2. **Sync ("סנכרון").** The app opens a background tab in Chrome for each board (up to four), reads the boards side by
   side, each at the pace of an ordinary visitor, and closes each board's tab the moment its reading ends. A few
   minutes in all. Chrome has to stay open, and you can keep working in it meanwhile.
3. **The board.** Ads that fit come first, with a score and the reasons. Clicking an ad opens photos, a map, what is
   around, which boards it came from, and a link to the original ad on its board.
4. **Mark ads.** Favourite, contacted, visit, not relevant, and a free note.
5. **"Read the full ad".** The list gives only the basics. The button loads one ad's page and brings its full text
   and features.
6. **Search together.** `start-lan.cmd` instead of `start.cmd` also opens the app to devices on your home network.
   With the "שיתוף" (share) button you make an invite link for a partner: they see the search, mark ads and write
   notes. Without a link nobody sees anything.
7. **"What changed" ("🔄 מה השתנה").** After every sync a window shows what was added, what left the board, what
   was posted again and what changed (a price, for example). The button in the top bar opens it again, also for
   earlier syncs. An ad counts as gone only after its board was read to the end.
8. **"＋ Ad" ("＋ מודעה").** Saw a flat somewhere else (a group, a message, a board this app does not read)?
   Paste its text: the app reads price, rooms, size, floor and address from it, scores it and compares it with
   the rest. The app fetches nothing by itself here: only what you pasted. A phone number in the text stays
   with you and shows in the ad with a call button.
9. **Up to 3 places in one search.** In the questionnaire you type the name of a city or town (in Hebrew or in
   English) and pick it; you can add two more (a city and the towns next to it, for example) and choose
   neighbourhoods for each. The limit is 3 to keep a reasonable load on the boards' servers: every extra place is
   one more search on every board, and the app rests 45 seconds between two places.
10. **"Automatic check" ("🔄 בדיקה אוטומטית").** On the first screen you can have the searches checked by
    themselves every 6 or 12 hours or once a day, for as long as the app and the browser are open. When a new flat
    fits, or the price of a fitting flat drops, a desktop notice pops up. It is off until you switch it on.
11. **Delete a search.** The small bin on the search's card on the first screen. The file is not erased: it moves
    to `data/removed`.
12. **Without a mouse, and with a screen reader.** Every button, row and window is reached with Tab and pressed
    with Enter; Esc closes; every button has a name a screen reader says. "🔊 Read the ad aloud" reads it with the
    browser's voice: all of it, in short, or only what the owner wrote, at the speed and voice you choose (in
    Hebrew only if the browser has a Hebrew voice).
13. **A light or a dark look.** The "Look" link at the bottom of the screen switches: as the computer is, light,
    dark. The choice is kept in the browser.
14. **"System status".** A link at the bottom of the screen: when each thing the app depends on was last updated
    (the Bank of Israel interest, each board, the extension, the searches, the automatic check, places around, the
    version check). When something did not update or failed, the link is marked ⚠️, and the app goes on with the
    last copy it kept. A buyer's card also says so when the interest is old.

Contacting the owner is something you do yourself, on the board.

## ⚠️ Limits worth knowing

**How ads are pulled**

- **Only when you ask.** A sync happens when you click, with Chrome open and the extension installed. The
  automatic check runs only if you switched it on, and at most once every 6 hours.
- **Slow on purpose.** The boards are read side by side, but each board gets one request at a time, with pauses.
  Once or twice a day is enough. Frequent syncs will make the boards block your browser.
- **Boards change their sites.** When one does, reading that board breaks until the code is updated.

**Board by board**

| Board | What to know |
|---|---|
| yad2 | The fullest board. A big search (more than 320 ads, all that yad2's lists show) is read in parts by number of rooms, and by price where needed, to its end (in a test: Petah Tikva, 785 of 786 in three and a half minutes). For some ads the map pin is off by a few hundred metres (that is how yad2 gives it) |
| Madlan | Sometimes shows a "press and hold" check. The app does not try to pass it, and nobody will do it for you: open Madlan, press and hold, then click "פתרתי" ("solved") in the app. Pulled at most once every 6 hours, and up to 5 full ads each time |
| Komo | Shows only the first 20 ads unless you are signed in. If you sign in to Komo in Chrome (yourself), the app reads all the pages. No map pin: the location comes from the address |
| Homeless | Up to 8 results pages are read, one at a time. No house number, so an ad is placed at the middle of its street |

**What the app covers**

- **Rent or buy, one of them per profile.** For a purchase the market comparison is by price per square metre
  against similar flats nearby. "Key money" ads (דמי מפתח) do not count as a fit, and a price far below its
  surroundings is marked "odd price" rather than a bargain. New from a developer, needs renovation, urban renewal
  and a flat with a tenant are marked from what the ad says, so they can be wrong.
- **A purchase search has far more ads.** yad2 is read in parts, like a big rental search (up to 30 parts; for a
  purchase this was not yet tried live), and Komo up to 6 pages. A very wide search may still not be read to its
  end, and the app says so: narrow the budget and the rooms. Developers' projects that yad2 lists separately are
  left out.
- **A buyer's numbers:** every ad in a search to buy has a card "What buying it would cost": the purchase tax by the
  Tax Authority's steps (your only home, or an additional one), the cash you need in hand, and an estimated monthly
  payment at the average interest the Bank of Israel publishes. It is an estimate, not advice: no reliefs (new
  immigrants, disability, discounted-price programmes), no lawyer's or agent's fees, and a real mortgage is a mix
  of tracks. The price is the asking price in the ad.
- **Purchase was tested** in Petah Tikva on yad2, Komo and Homeless, and in Yokneam Illit on Madlan (the list was
  read; Madlan's full ads stopped at its human check).
- **1,201 cities and towns:** nearly every place in Israel that yad2 knows, from the official list of the Central
  Bureau of Statistics (the same codes yad2 uses). In the questionnaire you type a name, in Hebrew or English, and
  pick it. The 118 larger places also have a list of neighbourhoods; in a place without one the whole place is
  searched. 28 places are missing because no map point was found for them (mostly Bedouin tribes and very small
  villages). Tested in depth in Petah Tikva and Ramat Gan. Most places were checked on yad2 only: Komo, Homeless and
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
- **Not stored:** owners' names and phone numbers from the boards. (In an ad you pasted yourself the phone stays,
  on your computer.) The app only reads: it sends no messages and contacts nobody.
- **Where the app does connect:** the boards themselves (through your Chrome, like ordinary browsing); OpenStreetMap
  for map tiles, for finding addresses (an ad's street and city are sent) and for places around (the city's bounds
  are sent); Google Fonts and unpkg for a font and the map library; in the English interface, OpenFreeMap for a map with English names (free, no key); Google Maps only when you open Street View;
  and, in a search to buy, the Bank of Israel once a week for the average mortgage interest (two open addresses;
  nothing about you or a flat is sent).
- **Read aloud:** the "🔊" button in an ad uses the browser's own voice. With a voice installed on the computer
  nothing leaves it; a voice that works through the internet (some browsers have those) sends the text to the
  browser's maker, and the button says so.
- **Version check:** when it starts, and then twice a day, the app reads one small file from GitHub that says what
  the newest version is. Nothing about you, your searches or your computer goes with that request. To switch it
  off: `python app.py serve --no-update-check`.

## 🧩 What the extension may do

The extension was built only for this app:

- **Access to four sites only:** `yad2.co.il`, `madlan.co.il`, `komo.co.il`, `homeless.co.il`, and the app itself at
  `127.0.0.1:7461`. It cannot see or touch any other site or tab.
- **Four actions only:** open a page of one of the boards in a background tab of its own (one per board), read the
  ads from it, close that tab when the reading ends, and show a notification. Its tabs always open in the
  background and never take the screen.
- **After the app is updated** the extension reloads itself from the folder (what the reload arrow in
  `chrome://extensions` does).
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

- **One-click update:** when a new version is out the app tells you, shows what is new, and on "Update now" it
  downloads it from GitHub, replaces the program's files only and starts itself again. The `data` folder, with
  your searches, marks, people and settings, is not changed, and the files that were replaced are kept in
  `data/backup`. If the new version does not start, the previous one is put back by itself. The extension updates
  itself too; only if the app asks, click its reload arrow in `chrome://extensions`. "About" at the bottom of the
  screen shows the version and checks for an update now.
- **Updating by hand:** close the app and run `update.cmd` (macOS / Linux: `./update.sh`): the same thing, without
  the browser. `update.cmd --check` only shows what would change. In a version from before 1.2, which has no
  update yet: download the ZIP once more and replace the files (`data` stays), and reload the extension in
  `chrome://extensions`. The update is a plain download: nothing about you or your computer is sent.
- **Remove:** remove the extension in `chrome://extensions` and delete the folder. That is all: nothing was
  installed anywhere else.

## 🤝 Fair use

The tool is meant for a personal apartment search. It reads what you would see yourself while browsing, at a
person's pace, and sends you to the original ad on its board. Each board has its own terms of use, and keeping to
them is the responsibility of whoever uses the tool. Do not use it to collect ads in bulk, to pass them on, or to
get around blocks.

## 📜 Licence

Free for personal and any other non-commercial use, changes included:
[PolyForm Noncommercial 1.0.0](LICENSE.md). Selling the app or building a paid service on it needs permission.

**Not for commercial use.** Estate agents, agencies and businesses: if you need this for work, a version made for
you, or something else built, write to me, I would like to hear what you are missing:
[im@avniyay.in](mailto:im@avniyay.in) · [X: @avniyayin](https://x.com/avniyayin) ·
[boards.avniyay.in](https://boards.avniyay.in/)

## 🤖 For an AI agent

Have an AI agent that works on your computer? Give it this page's address and it can download, install and start
the app for you. Only the Chrome extension has to be loaded by you (step 3). `AGENTS.md` tells it how to install,
the shell commands, the local interface and the rules it has to keep.

## 🍪 Enjoyed the app?

The app is free and stays free. **[Did it help? Toss me a snack :)](https://treat.dogware.ai/)**
