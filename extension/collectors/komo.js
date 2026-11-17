// Reads a komo.co.il search tab. Loaded into the board's page by the extension, then called with a job:
//   {mode: "page"}                 -> the ads of the search page the tab is on
//   {mode: "details", ids: [...]}   -> the full record of each ad (small pages, fetched one at a time, slowly)
// Komo is plain server-rendered HTML: the markup is read. It stops at the first refusal.
globalThis.__luachCollectors = globalThis.__luachCollectors || {};
globalThis.__luachCollectors.komo = async (JOB) => {
  const PAUSE = 1600;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const errors = [];
  let refused = false;
  const page = async (url) => {
    try {
      const r = await fetch(url);
      if (!r.ok) { errors.push(`${r.status} ${url.slice(0, 120)}`); refused = true; return null; }
      return new DOMParser().parseFromString(await r.text(), "text/html");
    } catch (e) { errors.push(`${String(e).slice(0, 80)} ${url.slice(0, 120)}`); return null; }
  };
  const clean = (s) => (s || "").replace(/ /g, " ").replace(/\s+/g, " ").trim();
  const pic = (src) => {
    const n = /picNum=(\d+)/.exec(src || "");
    return n ? `https://www.komo.co.il/api/modaot/tmunot/showPic/list/?picSize=b&picNum=${n[1]}&luachNum=2` : null;
  };

  if (JOB.mode === "details") {
    const items = {};
    for (const id of JOB.ids) {
      if (refused) break;
      const doc = await page("/code/nadlan/details/?modaaNum=" + id);
      const el = doc && doc.getElementById("modaaRow" + id);
      if (el) {
        el.querySelectorAll("script,style").forEach((s) => s.remove());
        const lines = el.innerHTML.replace(/<br\s*\/?>/gi, "\n").replace(/<\/(div|li|p|tr|h\d|span|strong)>/gi, "\n")
          .replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").split("\n").map(clean).filter(Boolean);
        const after = (label) => { const i = lines.indexOf(label); return i >= 0 ? lines[i + 1] : null; };
        const before = (label) => { const i = lines.indexOf(label); return i > 0 ? lines[i - 1] : null; };
        const from = lines.indexOf("תיאור הנכס:");
        const to = lines.findIndex((l, i) => i > from && (l === "קרא עוד..." || l === "מצב הנכס" || l === "על הנכס:"));
        const info = (title) => clean([...el.querySelectorAll(".secondInfoElement")].find((x) =>
          clean(x.querySelector(".secondInfoElementTitle")?.textContent) === title)?.querySelector(".secondInfoElementContent")?.textContent);
        items[id] = {
          seller: clean(el.querySelector(".mefarsemNew")?.textContent), // the phone stays hidden behind its button: not read
          description: from >= 0 ? lines.slice(from + 1, to > from ? to : from + 12).join("\n") : null,
          entrance: before("תאריך כניסה"), condition: after("מצב הנכס"), floors: after("קומות בבניין"),
          arnona: after("ארנונה"), vaad: after("ועד בית"),
          on: [...el.querySelectorAll(".modaaWNewUl li")].map((li) => li.className.trim().split(/\s+/)).filter((c) => c.length > 1).map((c) => c[0]),
          classes: [...el.querySelectorAll(".modaaWNewUl li")].map((li) => li.className.trim()),
          parking: info("חניות"), balconies: info("מרפסות"),
          furniture: clean(el.querySelector(".furnitureDesc")?.textContent).replace(/^הסבר על הריהוט\s*:?\s*/, "") || null,
          images: [...new Set([...el.querySelectorAll("img")].map((i) => pic(i.getAttribute("src") || i.getAttribute("data-lazy"))).filter(Boolean))].slice(0, 12),
          address: decodeURIComponent(el.querySelector("#mapCanvasW")?.getAttribute("addr") || "") || null,
        };
      }
      await sleep(PAUSE);
    }
    return { items, errors, blocked: refused };
  }

  const rowsOf = (doc) => [...doc.querySelectorAll(".modaaRowAd")].map((row) => {
    const desc = clean(row.querySelector(".description")?.textContent);
    const m = /^(.*?)\s*([\d.]+)\s*חדרים\s*(?:\((\d+)\s*מ"ר\))?/.exec(desc) || [];
    const fl = /קומה:\s*(\S+)(?:\s*מתוך\s*(\d+))?/.exec(desc) || [];
    return {
      id: row.getAttribute("key"), title: clean(row.querySelector(".title")?.textContent),
      price: clean(row.querySelector(".price")?.textContent).replace(/[^\d]/g, "") || null,
      type: clean(m[1]) || null, rooms: m[2] || null, sqm: m[3] || null, floor: fl[1] || null, topFloor: fl[2] || null,
      image: pic(row.querySelector("img")?.getAttribute("src")),
    };
  }).filter((r) => r.id);
  const totalOf = (doc) => { const t = /נמצאו\s+([\d,]+)\s+מודעות/.exec(doc.body.textContent); return t ? +t[1].replace(/,/g, "") : null; };
  // Komo refuses a scripted request for a list page, so app.py walks the tab from page to page and this reads it.
  if (location.hostname.startsWith("account.")) return { login: true };
  const isSearch = !!document.querySelector("[name=cityName], [name=fromRooms]");
  if (!isSearch && !document.querySelector(".modaaRowAd")) return { errors: ["לא דף חיפוש של קומו: " + document.title] };
  // Signed out, Komo's top bar offers "התחבר"; signed in, it does not.
  const signedIn = ![...document.querySelectorAll("a, span, button, div")].some((e) => e.children.length === 0 && e.textContent.trim() === "התחבר");
  return { total: totalOf(document), ads: rowsOf(document), signedIn };
};
