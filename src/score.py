"""
Notation des annonces par l'IA (Google Gemini, palier gratuit).

Pour chaque annonce, l'IA renvoie :
  - note (0-100)     : à quel point ça colle à ta wishlist
  - garder (bool)    : false si un critère rédhibitoire est clairement violé
  - raisons (liste)  : 2-3 raisons très courtes
  - message_contact  : un message prêt à copier-coller (si l'annonce est gardée)

On envoie les annonces PAR LOTS pour économiser le quota gratuit.
Si l'IA est indisponible (quota, réseau), on NE casse pas le run : l'annonce est
transmise quand même, marquée "non notée", pour ne pas rater une pépite.
"""

import json
import re
import time

BATCH_SIZE = 12

SYSTEM = (
    "Tu es un assistant immobilier EXIGEANT et honnête. "
    "Tu tries des annonces pour un utilisateur selon SES critères personnels. "
    "Tu réponds UNIQUEMENT par du JSON valide, sans aucun texte autour."
)


def build_client(api_key: str):
    """Crée le client Gemini AVEC un timeout, pour ne jamais rester bloqué si l'API traîne."""
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20000))


# Si le modèle demandé n'existe plus (Google renomme parfois), on essaie ceux-ci.
_FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-1.5-flash"]


def _looks_like_model_error(e) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("not found", "404", "not supported", "unknown model", "no such model"))


def _is_transient(e) -> bool:
    """Erreur passagère côté Google (surcharge du modèle, coupure) -> ça vaut le coup de réessayer."""
    msg = str(e).lower()
    return any(k in msg for k in (
        "503", "unavailable", "overloaded", "high demand",
        "500", "internal error", "timeout", "deadline",
    ))


def _generate(client, model: str, prompt: str) -> str:
    """Appelle Gemini (timeout via le client). Au plus 3 modèles, 1 essai chacun -> jamais bloqué."""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        temperature=0.2,
    )
    candidates = ([model] + [m for m in _FALLBACK_MODELS if m != model])[:3]
    last_err = None
    for m in candidates:
        try:
            return client.models.generate_content(model=m, contents=prompt, config=cfg).text
        except Exception as e:
            last_err = e
            if _is_transient(e):
                time.sleep(2)                    # courte pause puis on tente un autre modèle
                continue
            if _looks_like_model_error(e):
                continue                         # modèle inconnu -> on tente un autre modèle
            raise                                # erreur "dure" (clé invalide...) -> inutile d'insister
    raise last_err


def score_listings(client, model: str, listings: list, profile: dict) -> list[dict]:
    """Renvoie une liste de résultats alignée, index par index, sur `listings`."""
    results: list = [None] * len(listings)
    for start in range(0, len(listings), BATCH_SIZE):
        batch = listings[start:start + BATCH_SIZE]
        try:
            parsed = _parse_json(_generate(client, model, _prompt(profile, batch)))
        except Exception as e:  # quota, réseau, modèle... on continue sans planter
            print(f"   ⚠️  IA indisponible sur ce lot ({type(e).__name__}: {e}).")
            parsed = []

        by_index = {}
        for obj in parsed:
            if isinstance(obj, dict) and "index" in obj:
                try:
                    by_index[int(obj["index"])] = obj
                except (ValueError, TypeError):
                    pass

        for i in range(len(batch)):
            obj = by_index.get(i)
            if obj is None:
                results[start + i] = {
                    "ia_ok": False, "note": None, "garder": True,
                    "raisons": ["(non évaluée par l'IA — quota ou erreur)"],
                    "message_contact": "",
                }
            else:
                results[start + i] = {
                    "ia_ok": True,
                    "note": _int(obj.get("note"), default=50),
                    "garder": bool(obj.get("garder", True)),
                    "raisons": _as_list(obj.get("raisons")),
                    "message_contact": (obj.get("message_contact") or "").strip(),
                }
        time.sleep(1)  # petite pause pour rester tranquille avec le quota gratuit
    return results


# ----------------------------- interne -----------------------------

def _prompt(profile: dict, batch: list) -> str:
    items = [{
        "index": i,
        "source": l.source,
        "titre": l.titre,
        "prix": l.prix,
        "surface_m2": l.surface,
        "pieces": l.pieces,
        "ville": l.ville,
        "dpe": l.dpe,
        "description": l.resume,
        "url": l.url,
    } for i, l in enumerate(batch)]

    return (
        "CRITÈRES DE L'UTILISATEUR (langage naturel) :\n"
        f"{profile.get('wishlist', '')}\n\n"
        "Repères chiffrés : "
        f"budget_max={profile.get('budget_max')}, surface_min={profile.get('surface_min')}, "
        f"pieces_min={profile.get('pieces_min')}, villes={profile.get('villes')}\n\n"
        "Annonces à évaluer (données parfois incomplètes, extraites d'e-mails) :\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        "Pour CHAQUE annonce, renvoie un objet avec EXACTEMENT ces clés :\n"
        '  "index" (entier, celui de l\'annonce),\n'
        '  "note" (entier 0-100 : à quel point ça colle à la wishlist),\n'
        '  "garder" (true/false : false si un critère rédhibitoire de la wishlist est clairement violé),\n'
        '  "raisons" (2 à 3 raisons TRÈS courtes, en français),\n'
        '  "message_contact" (message court, poli, personnalisé, en français, pour demander une visite ; '
        'chaîne vide "" si garder vaut false).\n'
        "N'invente aucune information manquante. "
        "Réponds par un TABLEAU JSON de ces objets, et RIEN d'autre."
    )


def _parse_json(text: str):
    if not text:
        return []
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else [data]


def _as_list(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    if v:
        return [str(v)]
    return []


def _int(v, default=0):
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return default
