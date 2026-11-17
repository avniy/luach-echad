// Reads a homeless.co.il tab. Loaded into the board's page by the extension, then called with a job:
//   {mode: "page"}                 -> the ads of the search page the tab is on
//   {mode: "details", ids: [...]}   -> the full record of each ad (fetched one at a time, slowly)
// Homeless is plain server-rendered HTML: a results table and an ad page. It stops at the first refusal.
globalThis.__luachCollectors = globalThis.__luachCollectors || {};
globalThis.__luachCollectors.homeless = async (JOB) => {
  const PAUSE = 1700;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || "").replace(/ /g, " ").replace(/\s+/g, " ").trim();
  const errors = [];
  const DEAL = location.pathname.startsWith("/sale") ? "sale" : "rent"; // the board the tab is on

  if (JOB.mode === "details") {
    const items = {};
    let refused = false;
    for (const id of JOB.ids) {
      if (refused) break;
      try {
        const r = await fetch(`/${DEAL}/viewad,${id}.aspx`);
        if (!r.ok) { errors.push(`${r.status} מודעה ${id}`); refused = true; break; }
        const doc = new DOMParser().parseFromString(await r.text(), "text/html");
        const og = doc.querySelector('meta[property="og:description"]')?.getAttribute("content") || "";
        const kv = {};
        doc.querySelectorAll(".IconOption h3").forEach((h3) => { kv[clean(h3.textContent).replace(/:$/, "")] = clean(h3.parentElement.textContent.replace(h3.textContent, "")); });
        const icon = (el) => (/([\w-]+)\.svg/.exec(el.querySelector("img")?.getAttribute("src") || "") || [])[1];
        const imgs = [...doc.querySelectorAll("img")].map((i) => i.getAttribute("src") || i.getAttribute("data-src") || "")
          .filter((s) => /uploads\.homeless\.co\.il\/(rent|sale)/.test(s)).map((s) => s.replace(/\/(300|1200)\//, "/"));
        items[id] = {
          description: og.includes(" - ") ? og.slice(og.indexOf(" - ") + 3) : null, // the owner's phone and name are not read
          on: [...doc.querySelectorAll(".IconOption.on")].map(icon).filter(Boolean),
          known: doc.querySelectorAll(".IconOption.on, .IconOption.off").length > 0,
          floor: kv["קומה"], sqm: kv['מ"ר'], entrance: kv["כניסה"], arnona2m: kv["ארנונה לחודשיים"],
          images: [...new Set(imgs)].slice(0, 12),
        };
      } catch (e) { errors.push(`${String(e).slice(0, 80)} מודעה ${id}`); }
      await sleep(PAUSE);
    }
    return { items, errors, blocked: refused };
  }

  const rows = [...document.querySelectorAll('tr[type="ad"]')];
  if (!rows.length && !document.querySelector("#mainresults, form")) return { errors: ["לא דף חיפוש של הומלס: " + document.title] };
  const ads = rows.map((row) => {
    const c = [...row.querySelectorAll("td")].map((td) => clean(td.innerText));
    const img = row.querySelector("img")?.getAttribute("src") || "";
    return { id: (row.id || "").replace("ad_", ""), type: c[2], city: c[3], hood: c[4], street: c[5], rooms: c[6], floor: c[7],
      price: (c[8] || "").replace(/[^\d]/g, ""), entrance: c[9], updated: c[10],
      image: /uploads\.homeless/.test(img) ? img.replace(/\/300\//, "/") : null };
  }).filter((a) => a.id);
  const hasNext = [...document.querySelectorAll("a")].some((a) => /^(הבא|לעמוד הבא|›|»)$/.test(clean(a.textContent)));
  return { ads, hasNext };
};
