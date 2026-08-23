"""Envoi des pépites sur Discord via un webhook (gratuit, aucune app à créer)."""

import time

import requests

MAX_DESC = 4000
COLOR_TOP = 0x2ECC71     # vert  (note >= 80)
COLOR_GOOD = 0xF1C40F    # jaune (note >= 70)
COLOR_INFO = 0x3498DB    # bleu  (non notée / autre)


def send_listing(webhook_url: str, lst, score: dict) -> bool:
    """Poste une annonce sous forme de belle "carte" Discord + message à copier."""
    note = score.get("note")
    raisons = score.get("raisons") or []
    message = (score.get("message_contact") or "").strip()

    desc_lines = [f"**Note : {note}/100**" if note is not None else "**Note : non évaluée**"]
    desc_lines += [f"• {r}" for r in raisons[:3]]
    if not score.get("ia_ok", True):
        desc_lines.append("_⚠️ l'IA n'a pas pu noter cette annonce — à vérifier toi-même._")

    embed = {
        "title": (lst.titre or "Annonce").strip()[:240] or "Annonce",
        "description": "\n".join(desc_lines)[:MAX_DESC],
        "color": _color(note),
        "fields": _fields(lst),
    }
    if lst.url:
        embed["url"] = lst.url
    if lst.image:
        embed["image"] = {"url": lst.image}

    payload = {"embeds": [embed]}
    if message:
        # Le message va dans le "content", en bloc de code -> facile à copier sur mobile/PC.
        payload["content"] = "✉️ **Message prêt à copier-coller :**\n```\n" + message[:1600] + "\n```"

    return _post(webhook_url, payload)


# ----------------------------- interne -----------------------------

def _color(note):
    if note is None:
        return COLOR_INFO
    if note >= 80:
        return COLOR_TOP
    if note >= 70:
        return COLOR_GOOD
    return COLOR_INFO


def _fields(lst):
    out = []

    def add(name, value):
        out.append({"name": name, "value": str(value)[:1024], "inline": True})

    if lst.prix is not None:
        unit = {"achat": "€", "location": "€ / mois"}.get(lst.type_bien, "€")
        add("💰 Prix", f"{lst.prix:,}".replace(",", " ") + f" {unit}")
    if lst.surface is not None:
        add("📐 Surface", f"{lst.surface} m²")
    if lst.pieces is not None:
        add("🚪 Pièces", lst.pieces)
    if lst.ville:
        add("📍 Ville", lst.ville)
    if lst.dpe:
        add("⚡ DPE", lst.dpe)
    add("🏷️ Source", lst.source)
    return out


def _post(webhook_url: str, payload: dict, tries: int = 3) -> bool:
    for _ in range(tries):
        r = requests.post(webhook_url, json=payload, timeout=20)
        if r.status_code == 429:  # trop de messages trop vite : on attend
            wait = 2.0
            try:
                wait = float(r.json().get("retry_after", 2))
            except Exception:
                pass
            time.sleep(wait + 0.5)
            continue
        if 200 <= r.status_code < 300:
            time.sleep(0.7)  # petite pause pour respecter le rythme Discord
            return True
        print(f"   ⚠️  Discord a répondu {r.status_code} : {r.text[:200]}")
        return False
    return False
