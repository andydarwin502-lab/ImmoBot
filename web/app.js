// --- Connexion à ta base (clé "publishable", faite pour le navigateur) ---
const SUPABASE_URL = "https://hbugmlasvnolojexywtz.supabase.co";
const SUPABASE_KEY = "sb_publishable_3tbAXDGGiwCXtx4hmbU4pA_uwMOCIE3";
const REST = `${SUPABASE_URL}/rest/v1/listings`;
const SETTINGS = `${SUPABASE_URL}/rest/v1/settings`;
const HEAD = { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, "Content-Type": "application/json" };

let filter = "all";
let cache = [];
let settings = {};
let gal = { imgs: [], i: 0 };
let sortBy = "travel";
let map, marker, workPick = null;
let travelBusy = false;                          // évite deux calculs de trajet en même temps
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const nlAsc = (x, y) => {                        // tri ascendant, valeurs inconnues à la fin
  if (x == null && y == null) return 0;
  if (x == null) return 1;
  if (y == null) return -1;
  return x - y;
};
const SORTERS = {
  travel:  (a, b) => nlAsc(a.travel_min, b.travel_min),
  recent:  (a, b) => String(b.first_seen || "").localeCompare(String(a.first_seen || "")),
  price:   (a, b) => nlAsc(a.rent, b.rent),
  surface: (a, b) => (b.area || 0) - (a.area || 0),
};

// ------- Chargement -------
async function load() {
  const list = document.getElementById("list");
  list.innerHTML = '<p class="empty">Chargement…</p>';
  try {
    await loadSettings();
    const res = await fetch(`${REST}?select=*&order=first_seen.desc&limit=300`, { headers: HEAD });
    if (!res.ok) throw new Error(res.status + " " + (await res.text()).slice(0, 120));
    cache = await res.json();
    render();
    computeTravel();                               // complète les temps de trajet manquants
  } catch (e) {
    list.innerHTML = `<p class="empty">Impossible de charger 😕<br><small>${esc(String(e))}</small></p>`;
  }
}

async function loadSettings() {
  try {
    const r = await fetch(`${SETTINGS}?select=*&limit=1`, { headers: HEAD });
    const rows = await r.json();
    settings = rows[0] || {};
  } catch (e) { settings = {}; }
  fillForm();
}

// ------- Temps de trajet (calculé ICI, dans le navigateur = ton IP perso, fiable) -------
// (Le collecteur tourne sur GitHub Actions dont l'IP est bloquée par le serveur OSRM
//  gratuit : c'est pourquoi les trajets manquaient. Ici, depuis ton téléphone, ça marche.)
function workCoords() {
  return [settings.work_lat || 48.8786, settings.work_lng || 2.7804];
}

async function osrmMinutes(lat, lng, wlat, wlng) {
  try {
    const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${lng},${lat};${wlng},${wlat}?overview=false`);
    if (!r.ok) return null;
    const routes = (await r.json()).routes || [];
    return routes.length ? Math.round(routes[0].duration / 60) : null;
  } catch (e) { return null; }
}

// Pas de coordonnées ? On géocode la ville (service adresse.data.gouv.fr, gratuit).
async function geocodeCity(city, postal) {
  const q = (city || "").trim() || (postal || "");
  if (!q) return null;
  try {
    let u = `https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&limit=1`;
    if (postal) u += `&postcode=${encodeURIComponent(postal)}&type=municipality`;
    const f = (((await (await fetch(u)).json()).features) || [])[0];
    if (!f) return null;
    const [lng, lat] = f.geometry.coordinates;
    return { lat, lng };
  } catch (e) { return null; }
}

function patchListing(id, body) {
  return fetch(`${REST}?id=eq.${id}`, { method: "PATCH", headers: { ...HEAD, Prefer: "return=minimal" }, body: JSON.stringify(body) }).catch(() => {});
}

// Remplit les trajets manquants. Après un changement de lieu de travail, saveSettings
// remet tous les travel_min à null → cette fonction les recalcule tous avec le nouveau lieu.
async function computeTravel() {
  if (travelBusy) return;
  travelBusy = true;
  const tried = new Set();                         // annonces déjà tentées (évite de boucler)
  try {
    while (true) {
      const a = cache.find((x) => x.travel_min == null && !tried.has(x.id));
      if (!a) break;
      const done = cache.filter((x) => x.travel_min != null).length;
      setToast(`🚗 Calcul des trajets… ${done}/${cache.length}`);
      if (a.lat == null || a.lng == null) {         // pas de coordonnées : géocode la ville
        const c = await geocodeCity(a.city, a.postal_code);
        if (!c) { tried.add(a.id); continue; }
        a.lat = c.lat; a.lng = c.lng;
        patchListing(a.id, { lat: c.lat, lng: c.lng });
      }
      const [wlat, wlng] = workCoords();            // relu à chaque fois (si le lieu change en cours)
      const m = await osrmMinutes(a.lat, a.lng, wlat, wlng);
      if (m != null) { a.travel_min = m; patchListing(a.id, { travel_min: m }); render(); }
      else { tried.add(a.id); }                      // échec réseau : on réessaiera plus tard
      await sleep(120);
    }
  } finally {
    travelBusy = false;
    setToast(null);
    render();
  }
}

function setToast(msg) {
  let t = document.getElementById("toast");
  if (!msg) { if (t) t.remove(); return; }
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
}

// ------- Rendu -------
function render() {
  const list = document.getElementById("list");
  let items = cache.slice();
  items.sort(SORTERS[sortBy] || SORTERS.travel);
  items = applyFilters(items);
  if (filter === "fav") items = items.filter(a => a.status === "favori");
  if (!items.length) {
    list.innerHTML = `<p class="empty">${filter === "fav" ? "Aucun favori pour l'instant ❤️" : "Aucune annonce ne correspond."}</p>`;
    return;
  }
  list.innerHTML = items.map(card).join("");
  list.querySelectorAll("[data-fav]").forEach(b => b.onclick = (e) => { e.stopPropagation(); toggleFav(b.dataset.fav, b); });
  list.querySelectorAll("[data-gallery]").forEach(p => p.onclick = () => openGallery(p.dataset.gallery));
}

function applyFilters(items) {
  const s = settings;
  return items.filter(a => {
    if (s.budget_max && a.rent && a.rent > s.budget_max) return false;
    if (s.surface_min && a.area && a.area < s.surface_min) return false;
    if (s.max_travel_min && a.travel_min != null && a.travel_min > s.max_travel_min) return false;
    return true;
  });
}

function card(a) {
  const imgs = a.images || [];
  const img = imgs[0] || "";
  const tm = a.travel_min;
  const tClass = tm == null ? "t-none" : tm <= 15 ? "t-top" : tm <= 25 ? "t-good" : "t-far";
  const meta = [a.area ? a.area + " m²" : "", a.rooms ? a.rooms + " pièces" : "", a.bedrooms ? a.bedrooms + " ch." : ""]
    .filter(Boolean).join(" · ");
  const fav = a.status === "favori";
  const q = encodeURIComponent(`${a.source || ""} ${a.title || ""} ${a.city || ""} ${a.rent || ""}€ ${a.area || ""}m2`);
  const link = a.url || `https://www.google.com/search?q=${q}`;
  const linkLabel = a.url ? "➜ Voir l'annonce" : "🔍 Chercher l'annonce";
  return `
  <article class="card">
    <div class="photo" data-gallery="${a.id}" style="${img ? `background-image:url('${esc(img)}')` : ""}">
      <span class="badge ${tClass}">🚗 ${tm == null ? "—" : tm + "′"}</span>
      <button class="heart ${fav ? "on" : ""}" data-fav="${a.id}">${fav ? "❤️" : "🤍"}</button>
      ${imgs.length > 1 ? `<span class="count">📷 ${imgs.length}</span>` : ""}
    </div>
    <div class="body">
      <div class="price">${a.rent ? a.rent + " €" : "—"} <span class="meta">${meta ? "· " + meta : ""}</span></div>
      <div class="loc">${esc(a.city || "")}${a.postal_code ? " (" + esc(a.postal_code) + ")" : ""}${a.dpe ? " · DPE " + esc(a.dpe) : ""}</div>
      <div class="actions">
        <a class="btn" href="${esc(link)}" target="_blank" rel="noopener">${linkLabel}</a>
        <span class="src">${esc(a.source || "")}</span>
      </div>
    </div>
  </article>`;
}

// ------- Favoris -------
async function toggleFav(id, btn) {
  const a = cache.find(x => String(x.id) === String(id));
  if (!a) return;
  const next = a.status === "favori" ? null : "favori";
  a.status = next;
  btn.textContent = next ? "❤️" : "🤍";
  try {
    await fetch(`${REST}?id=eq.${id}`, { method: "PATCH", headers: { ...HEAD, Prefer: "return=minimal" }, body: JSON.stringify({ status: next }) });
  } catch (e) { /* affichage optimiste */ }
  if (filter === "fav") render();
}

// ------- Galerie photos -------
function openGallery(id) {
  const a = cache.find(x => String(x.id) === String(id));
  if (!a || !a.images || !a.images.length) return;
  gal = { imgs: a.images, i: 0 };
  showGal();
  document.getElementById("lb").classList.add("on");
}
function showGal() {
  document.getElementById("lb-img").style.backgroundImage = `url('${esc(gal.imgs[gal.i])}')`;
  document.getElementById("lb-count").textContent = `${gal.i + 1} / ${gal.imgs.length}`;
}
function navGal(d) { if (gal.imgs.length) { gal.i = (gal.i + d + gal.imgs.length) % gal.imgs.length; showGal(); } }
function closeGal() { document.getElementById("lb").classList.remove("on"); }

// ------- Critères (réglages) -------
function openSettings() {
  fillForm();
  document.getElementById("settings").classList.add("on");
  setTimeout(initMap, 60);
}
function closeSettings() { document.getElementById("settings").classList.remove("on"); }

function initMap() {
  if (typeof L === "undefined") return;
  const lat = settings.work_lat || 48.8786, lng = settings.work_lng || 2.7804;
  if (!map) {
    map = L.map("map").setView([lat, lng], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
    marker = L.marker([lat, lng], { draggable: true }).addTo(map);
    marker.on("dragend", () => pickAt(marker.getLatLng()));
    map.on("click", (e) => { marker.setLatLng(e.latlng); pickAt(e.latlng); });
  } else {
    map.setView([lat, lng], 12);
    marker.setLatLng([lat, lng]);
  }
  workPick = null;
  setTimeout(() => map.invalidateSize(), 80);
}

async function pickAt(latlng) {
  workPick = { lat: latlng.lat, lng: latlng.lng };
  const label = await reverseGeocode(latlng.lat, latlng.lng);
  if (label) setVal("s-work", label);
}

async function reverseGeocode(lat, lng) {
  try {
    const r = await fetch(`https://api-adresse.data.gouv.fr/reverse/?lat=${lat}&lon=${lng}`);
    const j = await r.json();
    return (j.features && j.features[0]) ? j.features[0].properties.label : null;
  } catch (e) { return null; }
}

function fillForm() {
  setVal("s-work", settings.work_label || "");
  setVal("s-budget", settings.budget_max || "");
  setVal("s-surface", settings.surface_min || "");
  setVal("s-travel", settings.max_travel_min || "");
}

async function saveSettings() {
  const btn = document.getElementById("s-save");
  btn.disabled = true; btn.textContent = "…";
  const addr = getVal("s-work").trim();
  const patch = {
    budget_max: numOrNull("s-budget"),
    surface_min: numOrNull("s-surface"),
    max_travel_min: numOrNull("s-travel"),
    updated_at: new Date().toISOString(),
  };
  try {
    let coords = null, label = null;
    if (workPick) {                                   // point posé sur la carte = prioritaire
      coords = workPick; label = addr || null;
    } else if (addr && addr !== (settings.work_label || "")) {
      const g = await geocode(addr);
      if (!g) { alert("Adresse introuvable — réessaie, ou place le point sur la carte."); return; }
      coords = { lat: g.lat, lng: g.lng }; label = g.label;
    }
    let moved = false;
    if (coords) {
      moved = settings.work_lat == null
        || Math.abs(coords.lat - settings.work_lat) > 0.001
        || Math.abs(coords.lng - settings.work_lng) > 0.001;
      patch.work_lat = coords.lat; patch.work_lng = coords.lng; patch.work_label = label;
      if (moved) {                                   // lieu déplacé (~100 m) : on efface les trajets…
        await fetch(`${REST}?id=gt.0`, { method: "PATCH", headers: { ...HEAD, Prefer: "return=minimal" }, body: JSON.stringify({ travel_min: null }) });
        cache.forEach(x => x.travel_min = null);
      }
    }
    await fetch(`${SETTINGS}?id=eq.1`, { method: "PATCH", headers: { ...HEAD, Prefer: "return=minimal" }, body: JSON.stringify(patch) });
    Object.assign(settings, patch);
    workPick = null;
    closeSettings();
    render();
    if (moved) computeTravel();                      // …puis recalcule tout avec le nouveau lieu
  } catch (e) {
    alert("Erreur en enregistrant : " + e);
  } finally {
    btn.disabled = false; btn.textContent = "Enregistrer";
  }
}

async function geocode(q) {
  try {
    const r = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&limit=1`);
    const j = await r.json();
    const f = (j.features || [])[0];
    if (!f) return null;
    const [lng, lat] = f.geometry.coordinates;
    return { lat, lng, label: f.properties.label };
  } catch (e) { return null; }
}

// ------- utilitaires -------
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function getVal(id) { return document.getElementById(id).value; }
function setVal(id, v) { const el = document.getElementById(id); if (el) el.value = v; }
function numOrNull(id) { const v = parseInt(getVal(id), 10); return isNaN(v) ? null : v; }

// ------- Câblage -------
document.querySelectorAll(".tab[data-filter]").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab[data-filter]").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  filter = t.dataset.filter;
  render();
});
document.getElementById("refresh").onclick = load;
document.getElementById("sort").onchange = (e) => { sortBy = e.target.value; render(); };
document.getElementById("settings-btn").onclick = openSettings;
document.getElementById("s-cancel").onclick = closeSettings;
document.getElementById("s-save").onclick = saveSettings;
document.getElementById("settings").onclick = (e) => { if (e.target.id === "settings") closeSettings(); };
document.getElementById("lb-close").onclick = closeGal;
document.getElementById("lb-prev").onclick = () => navGal(-1);
document.getElementById("lb-next").onclick = () => navGal(1);
document.getElementById("lb").onclick = (e) => { if (e.target.id === "lb") closeGal(); };
let sx = 0;
const lb = document.getElementById("lb");
lb.addEventListener("touchstart", e => { sx = e.touches[0].clientX; }, { passive: true });
lb.addEventListener("touchend", e => { const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 40) navGal(dx < 0 ? 1 : -1); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
load();
