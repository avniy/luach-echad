// Reads a yad2.co.il search tab. Loaded into the board's page by the extension, then called with a job:
//   {mode: "feed", features: [...], maxPages: N}  -> every ad of the search, plus which ads have each feature
//   {mode: "details", ids: [...]}                 -> the full record of each ad
// One request at a time with a pause, the way a person paging the site loads them.
globalThis.__luachCollectors = globalThis.__luachCollectors || {};
globalThis.__luachCollectors.yad2 = async (JOB) => {
  const PAUSE = 450;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const errors = [];
  const getJson = async (url, opts) => {
    try {
      const r = await fetch(url, opts);
      if (!r.ok) { errors.push(`${r.status} ${url.slice(0, 120)}`); return null; }
      return await r.json();
    } catch (e) { errors.push(`${String(e).slice(0, 80)} ${url.slice(0, 120)}`); return null; }
  };

  if (JOB.mode === "details") {
    const items = {};
    for (const id of JOB.ids) {
      const j = await getJson(`https://gw.yad2.co.il/realestate-item/${id}`, { credentials: "include" });
      if (j && j.data) {
        const d = j.data;
        delete d.searchText;
        delete d.customer; // the owner's name and phone are not ours to keep
        if (d.metaData) delete d.metaData.images;
        items[id] = d;
      }
      await sleep(PAUSE);
    }
    return { items, errors };
  }

  const el = document.getElementById("__NEXT_DATA__");
  if (!el) {
    const check = /captcha|radware|shieldsquare/i.test(document.title + " " + document.body.innerText.slice(0, 600));
    return { blocked: check, errors: [check ? "יד2 מבקש אימות אנושי" : "לא דף חיפוש של יד2: " + document.title] };
  }
  const nd = JSON.parse(el.textContent);
  const feedQuery = (nd.props?.pageProps?.dehydratedState?.queries || []).find((q) =>
    String(q.queryKey?.[0]).endsWith("-feed") && q.queryKey?.[1]?.city);
  if (!feedQuery) return { errors: ["אין רשימת מודעות בדף: " + document.title] };
  const params = { ...feedQuery.queryKey[1] };
  delete params.page;

  const slim = (a) => ({
    token: a.token, adType: a.adType, price: a.price ?? null,
    rooms: a.additionalDetails?.roomsCount ?? null,
    sqm: a.additionalDetails?.squareMeter ?? a.metaData?.squareMeterBuild ?? null,
    property: a.additionalDetails?.property?.text ?? null,
    city: a.address?.city?.text ?? null, hood: a.address?.neighborhood?.text ?? null,
    street: a.address?.street?.text ?? null, houseNo: a.address?.house?.number ?? null,
    floor: a.address?.house?.floor ?? null, lat: a.address?.coords?.lat ?? null, lon: a.address?.coords?.lon ?? null,
    images: (a.metaData?.images || (a.metaData?.coverImage ? [a.metaData.coverImage] : [])).slice(0, 12),
    agency: a.customer?.agencyName ?? null, approvedAt: a.dates?.approvedAt ?? null, onMap: false,
  });
  const ads = {};
  const take = (list, fromMap) => {
    for (const a of list || []) {
      if (!a || !a.token || (a.adType !== "private" && a.adType !== "commercial")) continue;
      if (!ads[a.token]) ads[a.token] = slim(a);
      if (fromMap) ads[a.token].onMap = true;
    }
  };
  // "lookalike" holds ads outside the search and "yad1" holds building projects: both are left out.
  const BUCKETS = ["yad2", "private", "agency", "platinum", "trio", "booster", "kingOfTheHar", "leadingBroker"];
  const takeFeed = (data) => { for (const b of BUCKETS) take(data[b], false); };

  const first = feedQuery.state.data;
  takeFeed(first);
  const totalPages = first.pagination?.totalPages || 1;
  const total = first.pagination?.total ?? null;
  const lastPage = Math.min(totalPages, JOB.maxPages || 10);
  const slug = (nd.query?.slug || [])[0];
  const dataUrl = (pathAndQuery) => {
    const u = new URL(pathAndQuery, location.origin);
    return `/realestate/_next/data/${nd.buildId}${u.pathname.replace(/^\/realestate/, "")}.json${u.search}`;
  };
  let pagesRead = 1;
  for (let page = 2; page <= lastPage; page++) {
    const qs = new URLSearchParams({ ...params, page: String(page) });
    qs.delete("region");
    let j = await getJson(dataUrl(`/realestate/rent/${slug}?${qs}`), { headers: { "x-nextjs-data": "1" } });
    if (j?.pageProps?.__N_REDIRECT) {
      await sleep(PAUSE);
      j = await getJson(dataUrl("/realestate" + j.pageProps.__N_REDIRECT), { headers: { "x-nextjs-data": "1" } });
    }
    const q = (j?.pageProps?.dehydratedState?.queries || []).find((x) => x.queryKey?.[0] === feedQuery.queryKey[0]);
    if (q?.state?.data) { takeFeed(q.state.data); pagesRead++; } else errors.push(`עמוד ${page} חזר ריק`);
    await sleep(PAUSE);
  }

  // The map answers with up to 200 located ads per request; with a feature filter it tells which ads have it.
  const mapUrl = (extra) => "https://gw.yad2.co.il/realestate-feed/rent/map?" + new URLSearchParams({ ...params, ...extra });
  const base = await getJson(mapUrl({}), { credentials: "include" });
  const mapOk = !!base?.data?.markers;
  take(base?.data?.markers, true);
  await sleep(PAUSE);
  const features = {};
  for (const f of JOB.features || []) {
    const j = await getJson(mapUrl({ [f]: "1" }), { credentials: "include" });
    if (j?.data?.markers) { features[f] = j.data.markers.map((m) => m.token); take(j.data.markers, true); }
    await sleep(PAUSE);
  }
  return { total, totalPages, pagesRead, complete: pagesRead === totalPages, mapOk, ads: Object.values(ads), features, errors };
};
