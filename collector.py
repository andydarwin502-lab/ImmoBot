#!/usr/bin/env python3
"""
Collecteur — lit tes annonces Jinka (API) -> les range dans Supabase -> les note avec l'IA.
Tranche 1 (pas encore de notif push).

Env / secrets attendus :
  JINKA_ACCESS_TOKEN, SUPABASE_URL, SUPABASE_KEY (clé secrète),
  GEMINI_API_KEY (optionnel), GEMINI_MODEL (optionnel)
Lit aussi config/criteria.yml (wishlist + seuil, pour la note IA).
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import requests
import yaml

ROOT = Path(__file__).parent
JINKA = "https://api.jinka.fr/apiv2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


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

    # 1) Récupérer les annonces Jinka
    ads = fetch_jinka(token)
    print(f"🏠 {len(ads)} annonce(s) récupérée(s) depuis Jinka.")
    if not ads:
        print("✅ Rien à faire.")
        return 0

    rows = _dedup([map_ad(a) for a in ads])
    print(f"🧹 {len(rows)} annonce(s) après dédoublonnage.")

    # 2) Ranger dans Supabase (insère les nouvelles, laisse les notes existantes tranquilles)
    sb = Supabase(sb_url, sb_key)
    touched = sb.upsert_listings(rows)
    print(f"🗄️  {touched} ligne(s) écrite(s) dans la base.")

    # 3) Noter par l'IA les annonces pas encore notées
    to_score = sb.get_unscored()
    print(f"🧠 {len(to_score)} annonce(s) à noter…")
    if to_score:
        score_and_save(sb, to_score)

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

    ads, diag = [], True
    for alert in alerts:
        aid = alert.get("id") or alert.get("alert_id")
        if not aid:
            continue
        rd = s.get(f"{JINKA}/alert/{aid}/dashboard", timeout=25)
        if rd.status_code >= 400:
            print(f"   ⚠️ alerte {aid} status {rd.status_code}")
            continue
        chunk = _as_list(rd.json(), ("ads", "results", "data", "matches", "items"))
        if chunk and diag:                       # une seule fois : structure brute (pour trouver l'URL)
            print("   (diag) 1re annonce :", json.dumps(chunk[0], ensure_ascii=False)[:900])
            diag = False
        ads.extend(chunk)
        time.sleep(0.25)
    return ads


def map_ad(a: dict) -> dict:
    imgs = a.get("images") or []
    if isinstance(imgs, list):
        imgs = [i.get("url") if isinstance(i, dict) else i for i in imgs]
    return {
        "ext_id": str(a.get("id") or a.get("uuid") or a.get("external_id") or a.get("reference") or ""),
        "source": a.get("source"),
        "url": a.get("url") or a.get("link") or a.get("ad_url"),
        "title": a.get("title") or a.get("name"),
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
        "images": imgs[:10] if isinstance(imgs, list) else None,
    }


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

    def get_unscored(self, limit: int = 40) -> list:
        cols = "ext_id,source,title,rent,area,rooms,bedrooms,city,quartier,dpe,url"
        r = requests.get(
            f"{self.base}/listings?scored=is.false&select={cols}&limit={limit}",
            headers=self.h, timeout=30,
        )
        if r.status_code >= 300:
            print(f"   ⚠️ get_unscored status {r.status_code}: {r.text[:200]}")
            return []
        return r.json()

    def save_score(self, ext_id: str, note, reasons, message) -> None:
        body = {"note": note, "reasons": reasons, "message": message, "scored": True}
        r = requests.patch(
            f"{self.base}/listings?ext_id=eq.{ext_id}",
            headers={**self.h, "Prefer": "return=minimal"},
            data=json.dumps(body), timeout=30,
        )
        if r.status_code >= 300:
            print(f"   ⚠️ save_score {ext_id} status {r.status_code}")


# ----------------------------- Notation IA -----------------------------

def score_and_save(sb: "Supabase", rows: list) -> None:
    cfg = _load_criteria()
    profile = (cfg.get("profils") or {}).get("location") or {}
    seuil = int(cfg.get("seuil_note", 70))

    listings = [SimpleNamespace(
        source=r.get("source") or "Jinka",
        titre=r.get("title") or "",
        prix=r.get("rent"),
        surface=r.get("area"),
        pieces=r.get("rooms"),
        ville=r.get("city") or r.get("quartier"),
        dpe=r.get("dpe"),
        url=r.get("url") or "",
        resume=(f"{r.get('title') or ''} — {r.get('quartier') or ''} {r.get('city') or ''}, "
                f"{r.get('rooms') or '?'} pièces, {r.get('bedrooms') or '?'} chambres, "
                f"{r.get('area') or '?'} m², {r.get('rent') or '?'}€, DPE {r.get('dpe') or '?'}"),
    ) for r in rows]

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("   ⚠️ Pas de clé Gemini — annonces enregistrées sans note.")
        for r in rows:
            sb.save_score(r["ext_id"], None, ["(pas de clé IA)"], "")
        return

    from src import score as scoremod
    client = scoremod.build_client(api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    results = scoremod.score_listings(client, model, listings, profile)

    kept, done = 0, 0
    for r, res in zip(rows, results):
        if not res.get("ia_ok", True):
            continue  # IA en échec (ex: 503 surcharge) -> on laisse scored=false pour réessayer plus tard
        note = res.get("note")
        sb.save_score(r["ext_id"], note, res.get("raisons") or [], res.get("message_contact") or "")
        done += 1
        if note is not None and note >= seuil:
            kept += 1
    reste = len(rows) - done
    msg = f"   ✅ {done}/{len(rows)} notée(s) ; {kept} au-dessus du seuil ({seuil})."
    if reste:
        msg += f" ({reste} à réessayer au prochain passage — IA momentanément indispo)"
    print(msg)


# ----------------------------- utilitaires -----------------------------

def _load_criteria() -> dict:
    try:
        with open(ROOT / "config" / "criteria.yml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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
