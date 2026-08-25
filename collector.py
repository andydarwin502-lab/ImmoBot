#!/usr/bin/env python3
"""
Collecteur — lit tes annonces Jinka -> Supabase -> temps de trajet (voiture) + lien direct.
(Pas de note IA.)

Env / secrets : JINKA_ACCESS_TOKEN, SUPABASE_URL, SUPABASE_KEY.
Lieu de travail : table `settings` (sinon Disneyland Paris par défaut).
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
JINKA = "https://api.jinka.fr/apiv2"
OSRM = "https://router.project-osrm.org/route/v1/driving"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DEFAULT_WORK = (48.8786, 2.7804)


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass

    token = os.environ.get("JINKA_ACCESS_TOKEN")
    sb_url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    sb_key = os.environ.get("SUPABASE_KEY")
    if not token or not sb_url or not sb_key:
        print("❌ Il manque JINKA_ACCESS_TOKEN / SUPABASE_URL / SUPABASE_KEY.")
        return 1

    session, ads = fetch_jinka(token)
    print(f"🏠 {len(ads)} annonce(s) récupérée(s) depuis Jinka.")
    if not ads:
        print("✅ Rien à faire.")
        return 0

    rows = _dedup([map_ad(a) for a in ads])
    id2token = {str(a.get("id") or a.get("uuid") or ""): a.get("_alert_token") for a in ads}
    print(f"🧹 {len(rows)} annonce(s) après dédoublonnage.")

    sb = Supabase(sb_url, sb_key)
    print(f"🗄️  {sb.upsert_listings(rows)} ligne(s) écrite(s) dans la base.")

    enrich_travel(sb)
    enrich_urls(sb, session, id2token)

    print("✅ Terminé.")
    return 0


# ----------------------------- Jinka -----------------------------

def fetch_jinka(token: str):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA, "Accept": "application/json",
        "Authorization": f"Bearer {token.replace('Bearer ', '').strip()}",
    })
    ra = s.get(f"{JINKA}/alert", timeout=25)
    if ra.status_code >= 400:
        print(f"   ⚠️ /alert status {ra.status_code} — token expiré ? {ra.text[:200]}")
        return s, []
    alerts = _as_list(ra.json(), ("alerts", "data", "results"))

    ads = []
    for alert in alerts:
        aid = alert.get("id") or alert.get("alert_id")
        if not aid:
            continue
        rd = s.get(f"{JINKA}/alert/{aid}/dashboard", timeout=25)
        if rd.status_code >= 400:
            print(f"   ⚠️ alerte {aid} status {rd.status_code}")
            continue
        atoken = alert.get("token") or aid
        chunk = _as_list(rd.json(), ("ads", "results", "data", "matches", "items"))
        for ad in chunk:
            if isinstance(ad, dict):
                ad["_alert_id"] = aid
                ad["_alert_token"] = atoken
        ads.extend(chunk)
        time.sleep(0.25)
    return s, ads


def map_ad(a: dict) -> dict:
    imgs = a.get("images")
    if isinstance(imgs, str):
        imgs = [u.strip() for u in imgs.split(",") if u.strip()]
    elif isinstance(imgs, list):
        imgs = [i.get("url") if isinstance(i, dict) else i for i in imgs]
    else:
        imgs = []
    return {
        "ext_id": str(a.get("id") or a.get("uuid") or a.get("external_id") or a.get("reference") or ""),
        "source": a.get("source"),
        "url": a.get("url") or a.get("link") or a.get("ad_url"),
        "title": a.get("title") or a.get("name") or a.get("type"),
        "rent": _int(a.get("rent") or a.get("price")),
        "area": _int(a.get("area") or a.get("surface")),
        "rooms": _int(a.get("room")),
        "bedrooms": _int(a.get("bedroom")),
        "floor": None if a.get("floor") is None else str(a.get("floor")),
        "city": a.get("city"),
        "quartier": a.get("quartier"),
        "postal_code": (str(a.get("postal_code") or a.get("cp") or "") or None),
        "lat": a.get("lat"),
        "lng": a.get("lng"),
        "dpe": a.get("energy_dpe") or a.get("dpe"),
        "furnished": a.get("furnished"),
        "images": imgs[:12] or None,
    }


# ----------------------------- Lien direct vers l'annonce -----------------------------

def enrich_urls(sb: "Supabase", session, id2token: dict) -> None:
    todo = sb.get_needing_url()
    if not todo:
        print("🔗 Liens déjà résolus.")
        return
    print(f"🔗 {len(todo)} lien(s) à résoudre…")
    done, diag = 0, True
    for r in todo:
        token = id2token.get(r["ext_id"])
        if not token:
            continue
        url = resolve_url(session, token, r["ext_id"], diag)
        diag = False
        if url:
            sb.save_url(r["ext_id"], url)
            done += 1
        time.sleep(0.25)
    print(f"   ✅ {done}/{len(todo)} lien(s) trouvé(s).")


def resolve_url(session, alert_token, ad_id, diag=False):
    """Récupère l'URL réelle (source) de l'annonce via l'endpoint de vue Jinka."""
    candidates = [
        f"{JINKA}/alert_result_view_ad?ad={ad_id}&alert_token={alert_token}",
        f"{JINKA}/alert_result_view_ad?ad={ad_id}",
    ]
    for url in candidates:
        try:
            r = session.get(url, timeout=15, allow_redirects=True)
            if diag:
                print(f"   (diag lien) …{url.split('/apiv2/')[-1][:70]} -> {r.status_code} | final={str(r.url)[:90]} | body={r.text[:180]}")
            if str(r.url).startswith("http") and "jinka" not in str(r.url):
                return str(r.url)
            d = _try_json(r)
            for k in ("url", "ad_url", "source_url", "link", "redirect", "redirect_url", "webUrl", "original_url"):
                v = _dig(d, k)
                if isinstance(v, str) and v.startswith("http") and "jinka" not in v:
                    return v
        except Exception as e:
            if diag:
                print(f"   (diag lien) erreur : {e}")
    return None


def _try_json(r):
    try:
        return r.json()
    except Exception:
        return {}


# ----------------------------- Temps de trajet -----------------------------

def enrich_travel(sb: "Supabase") -> None:
    wlat, wlng = sb.get_work_coords() or DEFAULT_WORK
    todo = sb.get_needing_travel()
    if not todo:
        print("🚗 Trajets déjà calculés.")
        return
    print(f"🚗 {len(todo)} trajet(s) à calculer (vers {wlat:.4f},{wlng:.4f})…")
    done = 0
    for r in todo:
        mins = osrm_minutes(r.get("lat"), r.get("lng"), wlat, wlng)
        if mins is not None:
            sb.save_travel(r["ext_id"], mins)
            done += 1
        time.sleep(0.2)
    print(f"   ✅ {done}/{len(todo)} trajet(s) calculé(s).")


def osrm_minutes(lat, lng, wlat, wlng):
    if lat is None or lng is None:
        return None
    try:
        r = requests.get(f"{OSRM}/{lng},{lat};{wlng},{wlat}?overview=false", timeout=20)
        if r.status_code >= 400:
            return None
        routes = r.json().get("routes") or []
        return round(routes[0]["duration"] / 60) if routes else None
    except Exception:
        return None


# ----------------------------- Supabase -----------------------------

class Supabase:
    def __init__(self, url: str, key: str):
        self.base = f"{url}/rest/v1"
        self.h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def upsert_listings(self, rows: list) -> int:
        rows = [r for r in rows if r.get("ext_id")]
        if not rows:
            return 0
        r = requests.post(
            f"{self.base}/listings?on_conflict=ext_id",
            headers={**self.h, "Prefer": "resolution=merge-duplicates,return=representation"},
            data=json.dumps(rows), timeout=40,
        )
        if r.status_code >= 300:
            print(f"   ⚠️ upsert status {r.status_code}: {r.text[:300]}")
            return 0
        try:
            return len(r.json())
        except Exception:
            return 0

    def _get(self, query):
        r = requests.get(f"{self.base}/{query}", headers=self.h, timeout=30)
        return r.json() if r.status_code < 300 else []

    def get_needing_travel(self, limit=100):
        return self._get(f"listings?travel_min=is.null&lat=not.is.null&select=ext_id,lat,lng&limit={limit}")

    def get_needing_url(self, limit=100):
        return self._get(f"listings?url=is.null&select=ext_id&limit={limit}")

    def _patch(self, ext_id, body):
        requests.patch(f"{self.base}/listings?ext_id=eq.{ext_id}",
                       headers={**self.h, "Prefer": "return=minimal"},
                       data=json.dumps(body), timeout=30)

    def save_travel(self, ext_id, minutes):
        self._patch(ext_id, {"travel_min": minutes})

    def save_url(self, ext_id, url):
        self._patch(ext_id, {"url": url})

    def get_work_coords(self):
        try:
            rows = self._get("settings?select=work_lat,work_lng&limit=1")
            if rows and rows[0].get("work_lat") is not None:
                return (rows[0]["work_lat"], rows[0]["work_lng"])
        except Exception:
            pass
        return None


# ----------------------------- utilitaires -----------------------------

def _dig(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            got = _dig(v, key)
            if got is not None:
                return got
    elif isinstance(data, list):
        for v in data:
            got = _dig(v, key)
            if got is not None:
                return got
    return None


def _as_list(data, keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _dedup(rows: list) -> list:
    seen, out = set(), []
    for r in rows:
        k = r.get("ext_id")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _int(v):
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    sys.exit(main())
