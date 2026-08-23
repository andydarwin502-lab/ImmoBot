#!/usr/bin/env python3
"""
Bot immo perso — orchestrateur.

Enchaîne :  lire les mails -> extraire les annonces -> filtres de base ->
notation par l'IA -> notifier les pépites sur Discord -> marquer les mails lus.

Usage :
  python main.py --once             # un passage (c'est ce que lance GitHub Actions)
  python main.py --once --dry-run   # pareil mais AFFICHE au lieu d'envoyer sur Discord
  python main.py --fixtures         # teste sur les faux mails de tests/fixtures (hors-ligne)
  python main.py --fixtures --dry-run
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from src import dedupe, extract, mailbox, notify, score

ROOT = Path(__file__).parent
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser(description="Bot immo perso (alertes mail + IA + Discord)")
    ap.add_argument("--once", action="store_true", help="un seul passage")
    ap.add_argument("--dry-run", action="store_true", help="affiche au lieu d'envoyer sur Discord")
    ap.add_argument("--fixtures", action="store_true", help="teste hors-ligne sur tests/fixtures")
    args = ap.parse_args()
    try:
        return run(dry_run=args.dry_run, use_fixtures=args.fixtures)
    except KeyboardInterrupt:
        return 130


def run(dry_run: bool = False, use_fixtures: bool = False) -> int:
    cfg = _load_config()
    seuil = int(cfg.get("seuil_note", 70))
    profiles = cfg.get("profils", {}) or {}

    # 1) Récupérer les mails ------------------------------------------------
    imap = None
    if use_fixtures:
        mails = _load_fixtures()
        print(f"🧪 Mode test : {len(mails)} faux mail(s) chargé(s) depuis tests/fixtures.")
    else:
        user, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
        if not user or not pwd:
            print("❌ GMAIL_USER / GMAIL_APP_PASSWORD manquants (voir TUTO.md).")
            return 1
        imap = mailbox.connect(IMAP_HOST, user, pwd)
        mails = mailbox.fetch_unread(imap)
        print(f"📥 {len(mails)} nouveau(x) mail(s) non lu(s).")

    if not mails:
        print("✅ Rien de nouveau. À plus tard !")
        if imap:
            mailbox.logout(imap)
        return 0

    # 2) Extraire + 3) filtres de base -------------------------------------
    kept = []            # (listing, profile_key, profile)
    total = 0
    for mail in mails:
        try:
            listings = dedupe.dedupe(extract.extract_from_email(mail))
        except Exception as e:
            print(f"   ⚠️  Extraction impossible pour un mail ({e}).")
            continue
        total += len(listings)
        for lst in listings:
            pkey, profile = _choose_profile(lst, profiles)
            if not profile:
                continue
            ok, _why = _hard_filter(lst, profile)
            if ok:
                kept.append((lst, pkey, profile))

    print(f"🔎 {total} annonce(s) extraite(s), {len(kept)} passe(nt) les filtres de base.")

    # 4) Notation par l'IA (regroupée par profil) --------------------------
    pepites = _score_kept(kept, seuil)
    pepites.sort(key=lambda p: (p[1].get("note") is not None, p[1].get("note") or 0), reverse=True)
    print(f"⭐ {len(pepites)} pépite(s) à te notifier.")

    # 5) Notifier -----------------------------------------------------------
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    for lst, res in pepites:
        if dry_run or not webhook:
            _print_pepite(lst, res)
        else:
            try:
                notify.send_listing(webhook, lst, res)
            except Exception as e:
                print(f"   ⚠️  Envoi Discord échoué ({e}).")

    # 6) Marquer les mails lus (sauf en test / dry-run) --------------------
    if imap is not None:
        if not dry_run:
            for mail in mails:
                try:
                    mailbox.mark_read(imap, mail["uid"])
                except Exception as e:
                    print(f"   ⚠️  Marquage 'lu' échoué ({e}).")
        mailbox.logout(imap)

    print("✅ Terminé.")
    return 0


# ----------------------------- étapes internes -----------------------------

def _score_kept(kept: list, seuil: int) -> list:
    """Note les annonces retenues et renvoie les pépites [(listing, résultat), ...]."""
    if not kept:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    client = None
    if api_key:
        try:
            client = score.build_client(api_key)
        except Exception as e:
            print(f"   ⚠️  Init IA impossible ({e}).")
    else:
        print("   ⚠️  Pas de clé Gemini : annonces filtrées transmises sans note.")

    groups = defaultdict(list)
    for lst, pkey, profile in kept:
        groups[pkey].append((lst, profile))

    pepites = []
    for pkey, items in groups.items():
        listings = [it[0] for it in items]
        profile = items[0][1]
        if client is not None:
            results = score.score_listings(client, model, listings, profile)
        else:
            results = [{"ia_ok": False, "note": None, "garder": True,
                        "raisons": ["(pas de clé IA)"], "message_contact": ""} for _ in listings]

        for lst, res in zip(listings, results):
            # On garde si l'IA n'a pas pu noter (pour ne rien rater),
            # ou si la note atteint le seuil sans critère rédhibitoire.
            keep = (not res.get("ia_ok", True)) or (
                res.get("note") is not None
                and res["note"] >= seuil
                and res.get("garder", True) is not False
            )
            if keep:
                pepites.append((lst, res))
    return pepites


def _choose_profile(lst, profiles):
    """Associe une annonce au bon profil (location / achat) parmi ceux actifs."""
    active = {k: v for k, v in profiles.items() if v and v.get("actif")}
    if not active:
        return None, None
    if lst.type_bien in active:
        return lst.type_bien, active[lst.type_bien]
    if len(active) == 1:
        k = next(iter(active))
        return k, active[k]
    if "location" in active:               # type inconnu, on tente la location d'abord
        return "location", active["location"]
    k = next(iter(active))
    return k, active[k]


def _hard_filter(lst, profile):
    """Filtres éliminatoires côté code (avant l'IA). Renvoie (ok, raison_du_rejet).

    Règle prudente : on ne rejette JAMAIS sur une donnée absente (l'IA jugera).
    """
    villes = [v.lower() for v in (profile.get("villes") or [])]
    if villes and lst.ville:
        hay = f"{lst.titre} {lst.resume} {lst.ville}".lower()
        if not any(v in hay for v in villes):
            return False, "hors zone"
    if lst.prix is not None:
        if profile.get("budget_max") and lst.prix > profile["budget_max"]:
            return False, "trop cher"
        if profile.get("budget_min") and lst.prix < profile["budget_min"]:
            return False, "prix suspect (trop bas)"
    if lst.surface is not None and profile.get("surface_min") and lst.surface < profile["surface_min"]:
        return False, "surface trop petite"
    if lst.pieces is not None and profile.get("pieces_min") and lst.pieces < profile["pieces_min"]:
        return False, "pas assez de pièces"
    return True, ""


# ----------------------------- utilitaires -----------------------------

def _load_config():
    with open(ROOT / "config" / "criteria.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_env():
    """Charge un éventuel fichier .env (local uniquement ; ignoré sur GitHub)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def _load_fixtures():
    folder = ROOT / "tests" / "fixtures"
    mails = []
    for path in sorted(folder.glob("*.html")):
        source = path.stem.split("_")[0]
        mails.append({
            "uid": path.name,
            "from": f"alerte@{source}.fr",
            "subject": f"[TEST] Nouvelles annonces {source}",
            "html": path.read_text(encoding="utf-8", errors="replace"),
            "text": "",
        })
    return mails


def _print_pepite(lst, res):
    note = res.get("note")
    print("─" * 64)
    print(f"⭐ {note if note is not None else '?'}/100 — {(lst.titre or 'Annonce')[:80]}")
    meta = []
    if lst.prix is not None:
        meta.append(f"{lst.prix} €")
    if lst.surface is not None:
        meta.append(f"{lst.surface} m²")
    if lst.pieces is not None:
        meta.append(f"{lst.pieces} p.")
    if lst.ville:
        meta.append(lst.ville)
    meta.append(lst.source)
    print("   " + " · ".join(meta))
    print(f"   {lst.url}")
    for r in (res.get("raisons") or [])[:3]:
        print(f"   • {r}")
    msg = (res.get("message_contact") or "").strip()
    if msg:
        print("   ✉️  Message proposé :")
        for line in msg.splitlines():
            print(f"      {line}")


if __name__ == "__main__":
    sys.exit(main())
