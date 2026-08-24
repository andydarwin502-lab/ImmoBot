// --- Connexion à ta base (clé "publishable", faite pour le navigateur) ---
const SUPABASE_URL = "https://hbugmlasvnolojexywtz.supabase.co";
const SUPABASE_KEY = "sb_publishable_3tbAXDGGiwCXtx4hmbU4pA_uwMOCIE3";
const REST = `${SUPABASE_URL}/rest/v1/listings`;
const HEAD = { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, "Content-Type": "application/json" };

let filter = "all";
let cache = [];

async function load() {
  const list = document.getElementById("list");
  list.innerHTML = '<p class="empty">Chargement…</p>';
  try {
    const res = await fetch(`${REST}?select=*&order=note.desc.nullslast,first_seen.desc&limit=300`, { headers: HEAD });
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
  if (filter === "fav") items = items.filter(a => a.status === "favori");
  if (!items.length) {
    list.innerHTML = `<p class="empty">${filter === "fav" ? "Aucun favori pour l'instant ❤️" : "Aucune annonce pour l'instant."}</p>`;
    return;
  }
  list.innerHTML = items.map(card).join("");
  list.querySelectorAll("[data-fav]").forEach(b => b.onclick = () => toggleFav(b.dataset.fav, b));
}

function card(a) {
  const img = (a.images && a.images[0]) || "";
  const note = a.note;
  const nClass = note == null ? "n-none" : note >= 80 ? "n-top" : note >= 70 ? "n-good" : "n-low";
  const fav = a.status === "favori";
  const reasons = (a.reasons || []).filter(r => r && !String(r).startsWith("(")).slice(0, 3);
  const q = encodeURIComponent(`${a.source || ""} ${a.title || ""} ${a.city || ""} ${a.rent || ""}€ ${a.area || ""}m2`);
  const search = `https://www.google.com/search?q=${q}`;
  const meta = [a.area ? a.area + " m²" : "", a.rooms ? a.rooms + " pièces" : "", a.bedrooms ? a.bedrooms + " ch." : ""]
    .filter(Boolean).join(" · ");
  return `
  <article class="card">
    <div class="photo" style="${img ? `background-image:url('${esc(img)}')` : ""}">
      <span class="note ${nClass}">${note == null ? "—" : note}</span>
      <button class="heart ${fav ? "on" : ""}" data-fav="${a.id}">${fav ? "❤️" : "🤍"}</button>
    </div>
    <div class="body">
      <div class="price">${a.rent ? a.rent + " €" : "—"} <span class="meta">${meta ? "· " + meta : ""}</span></div>
      <div class="loc">${esc(a.city || "")}${a.postal_code ? " (" + esc(a.postal_code) + ")" : ""}${a.dpe ? " · DPE " + esc(a.dpe) : ""}</div>
      ${reasons.length ? `<ul class="reasons">${reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      ${a.message ? `<details class="msg"><summary>✉️ Message pré-rédigé</summary><p>${esc(a.message)}</p></details>` : ""}
      <div class="actions">
        <a class="btn" href="${search}" target="_blank" rel="noopener">🔍 Chercher l'annonce</a>
        <span class="src">${esc(a.source || "")}</span>
      </div>
    </div>
  </article>`;
}

async function toggleFav(id, btn) {
  const a = cache.find(x => String(x.id) === String(id));
  if (!a) return;
  const next = a.status === "favori" ? null : "favori";
  a.status = next;
  btn.textContent = next ? "❤️" : "🤍";
  try {
    await fetch(`${REST}?id=eq.${id}`, {
      method: "PATCH",
      headers: { ...HEAD, Prefer: "return=minimal" },
      body: JSON.stringify({ status: next }),
    });
  } catch (e) { /* on garde l'affichage optimiste */ }
  if (filter === "fav") render();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.querySelectorAll(".tab[data-filter]").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  filter = t.dataset.filter;
  render();
});
document.getElementById("refresh").onclick = load;

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
load();
