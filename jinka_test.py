#!/usr/bin/env python3
"""SPIKE Jinka — vérifie qu'on lit tes annonces via l'API. N'affiche jamais le token."""

import os
import sys
from pathlib import Path

import requests

BASE = "https://api.jinka.fr/apiv2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
    except Exception:
        pass

    token = os.environ.get("JINKA_ACCESS_TOKEN")
    email = os.environ.get("JINKA_EMAIL")
    pwd = os.environ.get("JINKA_PASSWORD")

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})

    if token:
        token = token.replace("Bearer ", "").strip()
        s.headers["Authorization"] = f"Bearer {token}"
        try:
            s.cookies.set("LA_API_TOKEN", token, domain=".jinka.fr")
        except Exception:
            pass
        print("🔑 Utilisation du token Jinka (masqué).")
    elif email and pwd:
        print("🔐 Connexion à Jinka (email/mot de passe)…")
        r = s.post(f"{BASE}/user/auth", json={"email": email, "password": pwd}, timeout=25)
        print(f"   status login = {r.status_code}")
        if r.status_code >= 400:
            print(f"   réponse : {r.text[:300]}")
            return 1
        tok = _dig(_json(r), "access_token") or _dig(_json(r), "token")
        if tok:
            s.headers["Authorization"] = f"Bearer {tok}"
    else:
        print("❌ Mets JINKA_ACCESS_TOKEN (recommandé) OU JINKA_EMAIL + JINKA_PASSWORD.")
        return 1

    print("📋 Récupération de tes alertes…")
    ra = s.get(f"{BASE}/alert", timeout=25)
    print(f"   status alertes = {ra.status_code}")
    if ra.status_code >= 400:
        print(f"   réponse : {ra.text[:300]}")
        print("❌ Auth refusée : token expiré ou mal copié. Ré-extrais-le et recommence.")
        return 1
    alerts = _list(_json(ra), ("alerts", "data", "results"))
    print(f"   ✅ {len(alerts)} alerte(s).")
    if not alerts:
        print("   ⚠️ Aucune alerte : crée une recherche sur Jinka, enregistre-la, puis relance.")
        return 0

    first = alerts[0]
    aid = first.get("id") or first.get("alert_id")
    print(f"🏠 Annonces de l'alerte « {first.get('name') or first.get('title') or aid} »…")
    rd = s.get(f"{BASE}/alert/{aid}/dashboard", timeout=25)
    print(f"   status annonces = {rd.status_code}")
    if rd.status_code >= 400:
        print(f"   réponse : {rd.text[:300]}")
        return 1
    ads = _list(_json(rd), ("ads", "results", "data", "matches", "items"))
    print(f"   ✅ {len(ads)} annonce(s) dans cette alerte.")
    if ads:
        print(f"   champs dispo : {_keys(ads[0])}")
        for ad in ads[:5]:
            prix = ad.get("rent") or ad.get("price") or ad.get("buy") or "?"
            surf = ad.get("area") or ad.get("surface") or "?"
            ville = ad.get("city") or ad.get("ville") or "?"
            print(f"      • {prix}€ · {surf}m² · {ville} · {ad.get('source') or ''}")
    print("\n🎉 SUCCÈS : on lit bien tes annonces Jinka par API. Façon B validée depuis GitHub !")
    return 0


def _json(r):
    try:
        return r.json()
    except Exception:
        return {}


def _keys(d):
    return list(d.keys())[:25] if isinstance(d, dict) else type(d).__name__


def _dig(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            got = _dig(v, key)
            if got is not None:
                return got
    return None


def _list(data, keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
    return []


if __name__ == "__main__":
    sys.exit(main())
