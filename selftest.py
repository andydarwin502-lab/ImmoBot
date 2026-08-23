#!/usr/bin/env python3
"""TEST COMPLET — fabrique 2 fausses annonces, les note (Gemini) et les envoie sur Discord."""
import os
import sys

from src import notify, score
from src.extract import Listing


def main() -> int:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("❌ DISCORD_WEBHOOK_URL manquant.")
        return 1

    demo = [
        Listing(source="TEST", titre="✅ TEST — Bel appartement T3 lumineux",
                url="https://example.com/annonce/1", prix=780, surface=62, pieces=3,
                ville="Serris", dpe="C", type_bien="location",
                resume="Lumineux et calme, balcon, proche RER A, cuisine équipée, DPE C. 62 m², 3 pièces, 780 € à Serris (77700)."),
        Listing(source="TEST", titre="✅ TEST — Studio sombre sur rue",
                url="https://example.com/annonce/2", prix=650, surface=41, pieces=2,
                ville="Chessy", dpe="F", type_bien="location",
                resume="Studio sombre en rez-de-chaussée sur rue passante, vis-à-vis direct, DPE F. 41 m², 2 pièces, 650 € à Chessy (77700)."),
    ]
    profile = {"wishlist": "Lumineux, calme, pas de rez-de-chaussée, proche transports, DPE correct. Je fuis sombre, bruyant, DPE F/G.",
               "budget_max": 850, "surface_min": 40, "pieces_min": 2, "villes": ["77700"]}

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            client = score.build_client(api_key)
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
            results = score.score_listings(client, model, demo, profile)
            print("🧠 IA Gemini : OK")
        except Exception as e:
            print(f"⚠️  IA indisponible ({type(e).__name__}: {e}).")
            results = _demo_results()
    else:
        print("⚠️  Pas de clé Gemini — cartes sans note IA.")
        results = _demo_results()

    sent = 0
    for lst, res in zip(demo, results):
        try:
            if notify.send_listing(webhook, lst, res):
                sent += 1
        except Exception as e:
            print(f"   ⚠️  Envoi Discord échoué ({e}).")

    print(f"📨 {sent}/{len(demo)} carte(s) envoyée(s) sur Discord.")
    if sent:
        print("✅ SUCCÈS : va voir ton salon Discord, tu dois avoir des cartes de TEST. 🎉")
        return 0
    print("❌ Aucune carte envoyée — vérifie DISCORD_WEBHOOK_URL.")
    return 1


def _demo_results():
    return [
        {"ia_ok": True, "note": 88, "garder": True,
         "raisons": ["Lumineux et calme", "Proche RER A", "DPE C correct"],
         "message_contact": "Bonjour, votre annonce m'intéresse. Serait-il possible de convenir d'une visite ? Merci !"},
        {"ia_ok": True, "note": 42, "garder": True,
         "raisons": ["Sombre et sur rue passante", "DPE F"],
         "message_contact": ""},
    ]


if __name__ == "__main__":
    sys.exit(main())
