// The whole extension. It serves one program: the "לוח אחד" app on this computer (127.0.0.1:7461).
// The app asks for one of four things, and nothing else is possible:
//   navigate {url}          open a page of one of the four boards in the extension's own background tab for that board
//   collect  {board, job}   read that page with the script in collectors/<board>.js (shipped with the extension)
//   close    {board}        close that board's work tab: its reading is done
//   notify   {title, text, url}   a desktop note ("Komo asks to sign in again")
// It never types, clicks, signs in or sends anything to a board, and it cannot touch any other site or tab.
// Its work tabs are always opened in the background and never take the screen or the keyboard.
// After the app was updated, the app says which version of the extension its folder holds; when that is not the
// one running, the extension reloads itself from the folder (what the reload arrow in chrome://extensions does).

const APP = "http://127.0.0.1:7461";
const BOARDS = { yad2: "yad2.co.il", madlan: "madlan.co.il", komo: "komo.co.il", homeless: "homeless.co.il" };
const IDLE_CLOSE_MS = 120000;   // a work tab the app did not close (the app was stopped) closes after two idle minutes
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const boardOf = (url) => {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:") return null;
    return Object.keys(BOARDS).find((b) => u.hostname === BOARDS[b] || u.hostname.endsWith("." + BOARDS[b])) || null;
  } catch (e) { return null; }
};

// ---- the work tabs: one background tab per board, remembered while the browser session lasts ----
// The boards are read side by side, so each has a tab of its own; one board never has two requests at once.
const key = (board) => "tab_" + board;

async function workTab(board) {
  const id = (await chrome.storage.session.get(key(board)))[key(board)];
  if (id == null) return null;
  try { return await chrome.tabs.get(id); } catch (e) { return null; }
}

function loaded(getId, ms) {
  // Resolves when the tab reports "complete" (or after ms: some pages never stop loading their trackers).
  return new Promise((resolve) => {
    const seen = new Set();
    const done = (how) => { chrome.tabs.onUpdated.removeListener(on); clearInterval(look); clearTimeout(limit); resolve(how); };
    const on = (id, info) => { if (info.status === "complete") { seen.add(id); if (id === getId()) done("complete"); } };
    chrome.tabs.onUpdated.addListener(on);
    const look = setInterval(() => { if (seen.has(getId())) done("complete"); }, 100);
    const limit = setTimeout(() => done("timeout"), ms);
  });
}

async function navigate({ url }) {
  const board = boardOf(url);
  if (!board) throw new Error("כתובת שאינה של אחד מארבעת הלוחות");
  let id = null;
  const wait = loaded(() => id, 45000);
  const tab = await workTab(board);
  if (tab) { await chrome.tabs.update(tab.id, { url }); id = tab.id; }
  else {
    const made = await chrome.tabs.create({ url, active: false });
    await chrome.storage.session.set({ [key(board)]: made.id });
    id = made.id;
  }
  chrome.tabs.update(id, { autoDiscardable: false }).catch(() => {});
  const how = await wait;
  await sleep(400);
  const now = await chrome.tabs.get(id);
  return { url: now.url, title: now.title, loaded: how };
}

async function collect({ board, job }) {
  if (!BOARDS[board]) throw new Error("לוח לא מוכר");
  const tab = await workTab(board);
  if (!tab) throw new Error("אין דף פתוח של הלוח");
  if (boardOf(tab.url) !== board) {
    // The board sent the tab somewhere else (a check on another address, or an error page): nothing to read.
    let host = "";
    try { host = new URL(tab.url).hostname; } catch (e) { /* no address */ }
    return { blocked: true, errors: ["הלוח העביר לדף אחר: " + host] };
  }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", files: [`collectors/${board}.js`] });
  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, world: "MAIN", args: [board, job || {}],
    func: async (b, j) => {
      try { return { ok: true, value: await globalThis.__luachCollectors[b](j) }; }
      catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
    },
  });
  const out = res && res.result;
  if (!out) throw new Error("הדף לא ענה");
  if (!out.ok) throw new Error(out.error);
  return out.value;
}

async function close({ board }) {
  if (!BOARDS[board]) throw new Error("לוח לא מוכר");
  const tab = await workTab(board);
  await chrome.storage.session.remove(key(board));
  if (tab) await chrome.tabs.remove(tab.id).catch(() => {});
  return !!tab;
}

// A note may open one of the four boards, or the app itself on this computer (a search with new flats).
const opens = (url) => !!boardOf(url) || String(url || "").startsWith("http://127.0.0.1:7461/");
async function notify({ title, text, url }) {
  const id = opens(url) ? url : "luach-" + Date.now();
  await chrome.notifications.create(id, { type: "basic", iconUrl: "icon-128.png", title: String(title || "לוח אחד").slice(0, 80),
    message: String(text || "").slice(0, 300) });
  return true;
}
chrome.notifications.onClicked.addListener((id) => {
  if (opens(id)) chrome.tabs.create({ url: id });
  chrome.notifications.clear(id);
});

const COMMANDS = { navigate, collect, close, notify };

// ---- talking to the app: ask for the next request; each request is done on its own and answered when ready ----
let running = false;

async function call(body) {
  const r = await fetch(APP + "/api/ext/poll", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Luach-Extension": chrome.runtime.getManifest().version },
    body: JSON.stringify(Object.assign({ version: chrome.runtime.getManifest().version }, body)),
  });
  if (!r.ok) throw new Error("app " + r.status);
  const out = await r.json();
  if (out.reload && out.reload !== chrome.runtime.getManifest().version) {
    // The app's folder holds a newer extension than the one running: load it. The app asks once per version.
    setTimeout(() => chrome.runtime.reload(), 300);
    throw new Error("reloading");
  }
  return out.job;
}

async function run(job) {
  let done;
  try {
    if (!COMMANDS[job.cmd]) throw new Error("בקשה לא מוכרת: " + job.cmd);
    done = { id: job.id, ok: true, result: await COMMANDS[job.cmd](job.args || {}) };
  } catch (e) {
    done = { id: job.id, ok: false, error: String((e && e.message) || e) };
  }
  await chrome.storage.session.set({ lastJob: Date.now() });
  try { await call({ done }); } catch (e) { /* the app went away: it will ask again */ }
}

async function loop() {
  if (running) return;
  running = true;
  // A waiting request does not count as activity for Chrome; a small call every 20 s keeps the extension awake
  // for as long as the app is running.
  const awake = setInterval(() => chrome.runtime.getPlatformInfo(() => {}), 20000);
  try {
    for (;;) {
      const job = await call({});
      if (!job) continue;
      await chrome.storage.session.set({ lastJob: Date.now() });
      run(job);   // not awaited: the next board's request can start meanwhile
    }
  } catch (e) {
    // The app is not running (or was closed): stop asking. The alarm, or the app's page, starts it again.
  } finally {
    clearInterval(awake);
    running = false;
  }
}

async function tidy() {
  const { lastJob } = await chrome.storage.session.get("lastJob");
  if (lastJob && Date.now() - lastJob <= IDLE_CLOSE_MS) return;
  for (const board of Object.keys(BOARDS)) {
    const tab = await workTab(board);
    if (tab) await chrome.tabs.remove(tab.id).catch(() => {});
    await chrome.storage.session.remove(key(board));
  }
}

chrome.alarms.onAlarm.addListener(() => { tidy(); loop(); });
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create("luach", { periodInMinutes: 1 }); loop(); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create("luach", { periodInMinutes: 1 }); loop(); });
chrome.runtime.onMessage.addListener((msg, sender) => {
  // Only the app's own page may wake us (the content script runs nowhere else).
  if (msg && msg.wake && sender.url && /^http:\/\/(127\.0\.0\.1|localhost):7461\//.test(sender.url)) loop();
});
