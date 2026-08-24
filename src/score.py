"""
Notation des annonces par l'IA — via GROQ (gratuit, rapide, fiable).

API compatible OpenAI. Modèle par défaut : llama-3.3-70b-versatile.
Pour chaque annonce, l'IA renvoie note / garder / raisons / message_contact.
On envoie par LOTS. Si l'IA échoue, on NE casse pas le run (annonce "non notée",
elle sera réessayée plus tard).
"""

import json
import re
import time

import requests

BATCH_SIZE = 12
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_FALLBACK_MODELS = [
    "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it",
    "llama3-70b-8192", "llama3-8b-8192",
]

SYSTEM = (
    "Tu es un assistant immobilier EXIGEANT et honnête. "
    "Tu tries des annonces pour un utilisateur selon SES critères personnels. "
    "Tu réponds UNIQUEMENT par du JSON valide, sans aucun texte autour."
)


def build_client(api_key: str):
    """Crée une session HTTP authentifiée pour Groq."""
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    return s


def _generate(session, model: str, prompt: str) -> str:
    """Appelle Groq ; essaie plusieurs modèles ; jamais bloquant. Diagnostique si tout échoue."""
    candidates = [model] + [m for m in _FALLBACK_MODELS if m != model]
    last_err = None
    for m in candidates:
        try:
            payload = {
                "model": m,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            }
            r = session.post(GROQ_URL, data=json.dumps(payload), timeout=60)
            if r.status_code == 429 or r.status_code >= 500:      # surcharge -> modèle suivant
                last_err = RuntimeError(f"Groq {r.status_code}")
                time.sleep(2)
                continue
            if r.status_code == 404 or "model_not_found" in r.text or "does not exist" in r.text:
                last_err = RuntimeError(f"modèle '{m}' indispo")
                continue                                           # modèle inconnu -> suivant
            if r.status_code >= 400:                               # erreur dure (clé invalide...)
                raise RuntimeError(f"Groq {r.status_code}: {r.text[:200]}")
            return r.json()["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            last_err = e
            time.sleep(2)

    # Tout a échoué : on liste les modèles réellement disponibles (diagnostic).
    try:
        mr = session.get("https://api.groq.com/openai/v1/models", timeout=15)
        names = [x.get("id") for x in (mr.json().get("data") or [])]
        raise RuntimeError(f"aucun modèle Groq n'a marché — modèles dispo : {names}")
    except requests.RequestException:
        pass
    raise last_err or RuntimeError("Groq indisponible")


def score_listings(client, model: str, listings: list, profile: dict) -> list[dict]:
    """Renvoie une liste de résultats alignée, index par index, sur `listings`."""
    results: list = [None] * len(listings)
    for start in range(0, len(listings), BATCH_SIZE):
        batch = listings[start:start + BATCH_SIZE]
        raw = ""
        try:
            raw = _generate(client, model, _prompt(profile, batch))
            parsed = _parse_json(raw)
        except Exception as e:  # réseau, quota... on continue sans planter
            print(f"   ⚠️  IA indisponible sur ce lot ({type(e).__name__}: {e}).")
            parsed = []

        by_index = {}
        for pos, obj in enumerate(parsed):
            if not isinstance(obj, dict):
                continue
            try:
                idx = int(obj.get("index"))
            except (ValueError, TypeError):
                idx = pos               # pas d'index fourni par l'IA -> on prend la position
            by_index[idx] = obj

        if not by_index and raw:
            print(f"   (diag IA) réponse brute : {raw[:400]}")

        for i in range(len(batch)):
            obj = by_index.get(i)
            if obj is None:
                results[start + i] = {
                    "ia_ok": False, "note": None, "garder": True,
                    "raisons": ["(non évaluée par l'IA — à réessayer)"],
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
        time.sleep(0.5)
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
        "Annonces à évaluer (données parfois incomplètes) :\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        "Pour CHAQUE annonce, renvoie un objet avec EXACTEMENT ces clés :\n"
        '  "index" (entier, celui de l\'annonce),\n'
        '  "note" (entier 0-100 : à quel point ça colle à la wishlist),\n'
        '  "garder" (true/false : false si un critère rédhibitoire est clairement violé),\n'
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
    if isinstance(data, dict):
        for k in ("results", "annonces", "data", "items"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
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
