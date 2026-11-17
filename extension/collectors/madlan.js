// Reads a madlan.co.il tab: only the page that is open. Loaded into the page by the extension, called with a job:
//   {mode: "page", city: "<city name>"}  -> the ads of the search page the tab is on
//   {mode: "ad", id: "<listing id>"}     -> the full record of the ad page the tab is on
// Madlan answers scripted paging with a "press and hold" human check. So this script makes no requests of its own:
// the app walks the tab from page to page with pauses, the way a person browses, and this only reads what Madlan
// put in the page. It never tries to pass the check: a person has to.
globalThis.__luachCollectors = globalThis.__luachCollectors || {};
globalThis.__luachCollectors.madlan = async (JOB) => {
  const state = window.__SSR_HYDRATED_CONTEXT__?.reduxInitialState;
  const check = () => /press\s*&\s*hold/i.test(document.body.innerText) || !!document.querySelector("#px-captcha");

  if (JOB.mode === "ad") {
    const find = (o, depth) => {
      if (!o || typeof o !== "object" || depth > 7) return null;
      if (o.id === JOB.id && ("description" in o || "amenities" in o)) return o;
      for (const k of Object.keys(o)) { const r = find(o[k], depth + 1); if (r) return r; }
      return null;
    };
    const b = find(state?.domainData?.bulletinsByIds?.data, 0);
    if (!b) return check() ? { blocked: true, errors: ["מדלן מבקש אימות אנושי"] } : { errors: ["המודעה לא נמצאה בדף: " + document.title] };
    return { item: {
      description: b.description, amenities: b.amenities, floors: b.floors, availabilityType: b.availabilityType,
      availableDate: b.availableDate, furnitureDetails: b.furnitureDetails, monthlyTaxes: b.monthlyTaxes,
      commonCharges: b.commonCharges, parking: b.parking, balconyArea: b.balconyArea,
      generalCondition: b.generalCondition, closestRailStation: b.closestRailStation,
    } }; // the owner's name and phone (b.poc.contactInfo) are left behind on purpose
  }

  const list = state?.domainData?.searchList?.data?.searchPoiV2;
  if (!list) return check() ? { blocked: true, errors: ["מדלן מבקש אימות אנושי"] } : { errors: ["לא דף חיפוש של מדלן: " + document.title] };
  const slim = (p) => ({
    id: p.id, price: p.price, beds: p.beds, area: p.area, floor: p.floor, buildingClass: p.buildingClass,
    generalCondition: p.generalCondition,
    addressDetails: { city: p.addressDetails?.city, neighbourhood: p.addressDetails?.neighbourhood,
      streetName: p.addressDetails?.streetName, streetNumber: p.addressDetails?.streetNumber },
    locationPoint: p.locationPoint, images: (p.images || []).slice(0, 12).map((i) => ({ imageUrl: i.imageUrl })),
    poc: { type: p.poc?.type }, eventsHistory: p.eventsHistory, firstTimeSeen: p.firstTimeSeen,
    parkWalkTime: p.parkWalkTime,
    insights: (p.insights?.insights || []).map((i) => i.tradeoff?.value).filter(Boolean),
  });
  // The list ends with ads from nearby towns; only the profile's city is kept.
  const ads = (list.poi || []).filter((p) => p.type === "bulletin" && p.id && p.addressDetails?.city === JOB.city).map(slim);
  return { total: list.total ?? null, ads };
};
