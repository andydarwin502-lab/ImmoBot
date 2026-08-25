// --- Connexion à ta base (clé "publishable", faite pour le navigateur) ---
const SUPABASE_URL = "https://hbugmlasvnolojexywtz.supabase.co";
const SUPABASE_KEY = "sb_publishable_3tbAXDGGiwCXtx4hmbU4pA_uwMOCIE3";
const REST = `${SUPABASE_URL}/rest/v1/listings`;
const HEAD = { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, "Content-Type": "application/json" };

let filter = "all";
let cache = [];
let gal = { imgs: [], i: 0 };

async function load() {
  const list = document.getElementById("list");
  list.innerHTML = '<p class="empty">Chargement…</p>';
  try {
    const res = await fetch(`${REST}?select=*&order=first_seen.desc&limit=300`, { headers: HEAD });
    if (!res.ok) throw new Error(res.status + " " + (await res.text()).slice(0, 120));
    cache = await res.json();
    render();
  } catch (e) {
    list.innerHTML = `<p class="empty">Impossible de charger 😕<br><small>${esc(String(e))}</small></p>`;
  }
}

function render() {
  const list = document.getElementById("list");
  let items = cache.slice();
  items.sort((a, b) => {                       // trajet le plus court d'abord (inconnus à la fin)
    const ta = a.travel_min, tb = b.travel_min;
    if (ta == null && tb == null) return 0;
    if (ta == null) return 1;
    if (tb == null) return -1;
    return ta - tb;
  });
  if (filter === "fav") items = items.filter(a => a.status === "favori");
  if (!items.length) {
    list.innerHTML = `<p class="empty">${filter === "fav" ? "Aucun favori pour l'instant ❤️" : "Aucune annonce pour l'instant."}</p>`;
    return;
  }
  list.innerHTML = items.map(card).join("");
  list.querySelectorAll("[data-fav]").forEach(b => b.onclick = (e) => { e.stopPropagation(); toggleFav(b.dataset.fav, b); });
  list.querySelectorAll("[data-gallery]").forEach(p => p.onclick = () => openGallery(p.dataset.gallery));
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
  const search = `https://www.google.com/search?q=${q}`;
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
        <a class="btn" href="${search}" target="_blank" rel="noopener">🔍 Chercher l'annonce</a>
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

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ------- UI wiring -------
document.querySelectorAll(".tab[data-filter]").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  filter = t.dataset.filter;
  render();
});
document.getElementById("refresh").onclick = load;
document.getElementById("lb-close").onclick = closeGal;
document.getElementById("lb-prev").onclick = () => navGal(-1);
document.getElementById("lb-next").onclick = () => navGal(1);
document.getElementById("lb").onclick = (e) => { if (e.target.id === "lb") closeGal(); };
// swipe mobile
let sx = 0;
const lb = document.getElementById("lb");
lb.addEventListener("touchstart", e => { sx = e.touches[0].clientX; }, { passive: true });
lb.addEventListener("touchend", e => { const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 40) navGal(dx < 0 ? 1 : -1); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
load();
