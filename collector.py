#!/usr/bin/env python3
"""
Collecteur — lit tes annonces Jinka -> les range dans Supabase -> calcule le TEMPS DE TRAJET
en voiture vers ton travail. (Plus de note IA.)

Env / secrets : JINKA_ACCESS_TOKEN, SUPABASE_URL, SUPABASE_KEY.
Le lieu de travail vient de la table `settings` (sinon valeur par défaut : Disneyland Paris).
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
DEFAULT_WORK = (48.8786, 2.7804)  # Disneyland Paris (fallback si pas de settings)


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

    ads = fetch_jinka(token)
    print(f"🏠 {len(ads)} annonce(s) récupérée(s) depuis Jinka.")
    if not ads:
        print("✅ Rien à faire.")
        return 0

    rows = _dedup([map_ad(a) for a in ads])
    print(f"🧹 {len(rows)} annonce(s) après dédoublonnage.")

    sb = Supabase(sb_url, sb_key)
    touched = sb.upsert_listings(rows)
    print(f"🗄️  {touched} ligne(s) écrite(s) dans la base.")

    enrich_travel(sb)

    print("✅ Terminé.")
    return 0


# ----------------------------- Jinka -----------------------------

def fetch_jinka(token: str) -> list:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA, "Accept": "application/json",
        "Authorization": f"Bearer {token.replace('Bearer ', '').strip()}",
    })
    ra = s.get(f"{JINKA}/alert", timeout=25)
    if ra.status_code >= 400:
        print(f"   ⚠️ /alert status {ra.status_code} — token expiré ? {ra.text[:200]}")
        return []
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
        ads.extend(_as_list(rd.json(), ("ads", "results", "data", "matches", "items")))
        time.sleep(0.25)
    return ads


def map_ad(a: dict) -> dict:
    imgs = a.get("images")
    if isinstance(imgs, str):                 # Jinka renvoie souvent "url1,url2,..." (une chaîne)
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
        time.sleep(0.25)
    print(f"   ✅ {done}/{len(todo)} trajet(s) calculé(s).")


def osrm_minutes(lat, lng, wlat, wlng):
    """Temps de trajet voiture (minutes) via le serveur public OSRM. None si indispo."""
    if lat is None or lng is None:
        return None
    try:
        url = f"{OSRM}/{lng},{lat};{wlng},{wlat}?overview=false"
        r = requests.get(url, timeout=20)
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

    def get_needing_travel(self, limit: int = 100) -> list:
        r = requests.get(
            f"{self.base}/listings?travel_min=is.null&lat=not.is.null&select=ext_id,lat,lng&limit={limit}",
            headers=self.h, timeout=30,
        )
        if r.status_code >= 300:
            print(f"   ⚠️ get_needing_travel status {r.status_code}: {r.text[:200]}")
            return []
        return r.json()

    def save_travel(self, ext_id: str, minutes: int) -> None:
        r = requests.patch(
            f"{self.base}/listings?ext_id=eq.{ext_id}",
            headers={**self.h, "Prefer": "return=minimal"},
            data=json.dumps({"travel_min": minutes}), timeout=30,
        )
        if r.status_code >= 300:
            print(f"   ⚠️ save_travel {ext_id} status {r.status_code}")

    def get_work_coords(self):
        try:
            r = requests.get(f"{self.base}/settings?select=work_lat,work_lng&limit=1",
                             headers=self.h, timeout=20)
            if r.status_code >= 300:
                return None
            rows = r.json()
            if rows and rows[0].get("work_lat") is not None:
                return (rows[0]["work_lat"], rows[0]["work_lng"])
        except Exception:
            pass
        return None


# ----------------------------- utilitaires -----------------------------

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
