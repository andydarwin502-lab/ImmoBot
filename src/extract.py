"""
Extraction des annonces depuis le HTML des mails d'alerte.

Chaque site a une mise en page d'e-mail différente. On utilise donc une méthode
GÉNÉRIQUE et robuste : on repère les liens qui pointent vers une annonce, puis on
lit le prix / la surface / etc. dans le "bloc" (la carte) autour du lien.
Si un site change son format, il suffira d'ajuster ce fichier — le reste ne bouge pas.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

# Domaines de sites immo connus -> nom lisible de la source.
SOURCE_BY_DOMAIN = {
    "leboncoin.fr": "Leboncoin",
    "seloger.com": "SeLoger",
    "pap.fr": "PAP",
    "bienici.com": "Bien'ici",
    "logic-immo.com": "Logic-Immo",
    "orpi.com": "Orpi",
    "century21.fr": "Century 21",
    "avendrealouer.fr": "A Vendre A Louer",
    "immobilier.lefigaro": "Figaro Immo",
    "ouestfrance-immo.com": "Ouest-France Immo",
    "superimmo.com": "SuperImmo",
    "jinka.fr": "Jinka",
    "jinka.immo": "Jinka",
}

# Liens à ignorer (désabonnement, aide, réseaux sociaux, apps, etc.).
IGNORE_URL_PARTS = (
    "unsubscribe", "desabonnement", "desinscription", "preferences", "/settings",
    "mailto:", "tel:", "facebook.", "twitter.", "instagram.", "linkedin.",
    "youtube.", "apps.apple.", "play.google.", "/aide", "/help", "/cgu",
    "privacy", "confidentialite", "cookies",
)

PRICE_RE = re.compile(r"([0-9][0-9\s \.]{1,12})\s*€")
SURFACE_RE = re.compile(r"(\d{1,4}(?:[.,]\d)?)\s*m(?:²|2|\^2)", re.I)
PIECES_RE = re.compile(r"(\d{1,2})\s*(?:pi[eè]ces?|p\b)|\b[TF]\s?(\d)\b", re.I)
DPE_RE = re.compile(r"\bDPE\s*[:\-]?\s*([A-G])\b", re.I)
CITY_RE = re.compile(r"\b(\d{5})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]+(?:\s[A-Za-zÀ-ÿ'\-]+)?)")


@dataclass
class Listing:
    source: str = "Inconnu"
    titre: str = ""
    url: str = ""
    prix: int | None = None
    surface: int | None = None
    pieces: int | None = None
    ville: str | None = None
    dpe: str | None = None
    image: str | None = None
    type_bien: str | None = None   # "location", "achat" ou None
    resume: str = ""               # petit extrait de texte de la carte


def extract_from_email(mail: dict) -> list[Listing]:
    """Point d'entrée : un mail (dict) -> liste d'annonces."""
    html = mail.get("html") or ""
    subject = mail.get("subject") or ""
    sender = mail.get("from") or ""
    default_type = _guess_type_from_text(f"{subject} {sender}")

    if html.strip():
        listings = _extract_from_html(html, subject)
    else:
        listings = _extract_from_text(mail.get("text") or "", subject)

    for lst in listings:
        if lst.type_bien is None:
            lst.type_bien = default_type or _guess_type_from_price(lst.prix)
    return listings


def normalize_url(url: str) -> str:
    """Enlève les paramètres de tracking (?utm=...) pour comparer/dédoublonner."""
    try:
        p = urlparse(url)
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", "", ""))
    except Exception:
        return url


# ----------------------------- interne -----------------------------

def _soup(html: str):
    """Parse le HTML avec lxml si dispo, sinon le parseur intégré de Python."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _extract_from_html(html: str, subject: str) -> list[Listing]:
    soup = _soup(html)
    seen, listings = set(), []
    for a in soup.find_all("a", href=True):
        url = a["href"].strip()
        if not _looks_like_listing(url):
            continue
        key = normalize_url(url)
        if key in seen:
            continue
        seen.add(key)

        card = _closest_card(a)
        card_text = _clean_text(card.get_text(" ", strip=True)) if card else ""
        anchor_text = _clean_text(a.get_text(" ", strip=True))

        listings.append(Listing(
            source=_source_from_url(url) or "Inconnu",
            url=url,
            titre=anchor_text or _first_heading(card) or subject,
            prix=_to_int(_first_group(PRICE_RE, card_text)),
            surface=_to_int(_first_group(SURFACE_RE, card_text)),
            pieces=_pieces(card_text),
            dpe=_first_group(DPE_RE, card_text),
            image=_first_image(card),
            ville=_guess_city(card_text),
            resume=card_text[:400],
        ))
    return listings


def _extract_from_text(text: str, subject: str) -> list[Listing]:
    """Repli quand le mail n'a pas de version HTML : on cherche des URLs dans le texte."""
    seen, listings = set(), []
    for m in re.finditer(r"https?://[^\s>\)\"']+", text or ""):
        url = m.group(0)
        if not _looks_like_listing(url):
            continue
        key = normalize_url(url)
        if key in seen:
            continue
        seen.add(key)
        window = _clean_text(text[max(0, m.start() - 200): m.end() + 120])
        listings.append(Listing(
            source=_source_from_url(url) or "Inconnu",
            url=url,
            titre=subject,
            prix=_to_int(_first_group(PRICE_RE, window)),
            surface=_to_int(_first_group(SURFACE_RE, window)),
            pieces=_pieces(window),
            dpe=_first_group(DPE_RE, window),
            image=None,
            ville=_guess_city(window),
            resume=window[:400],
        ))
    return listings


def _looks_like_listing(url: str) -> bool:
    low = url.lower()
    if not low.startswith("http"):
        return False
    if any(bad in low for bad in IGNORE_URL_PARTS):
        return False
    src = _source_from_url(url)
    if not src:
        return False
    if src == "Jinka":
        return True   # les liens Jinka sont des redirections sans id numérique
    keywords = ("/annonce", "/ad/", "/vente", "/location", "/detail", "/bien", "/vi/")
    return bool(re.search(r"\d{6,}", low) or any(k in low for k in keywords))


def _source_from_url(url: str) -> str | None:
    low = url.lower()
    host = (urlparse(url).netloc or "").lower()
    for dom, label in SOURCE_BY_DOMAIN.items():
        if dom in host or dom in low:
            return label
    return None


def _closest_card(node):
    """Remonte de quelques niveaux pour trouver le bloc (carte) contenant l'annonce."""
    cur = node
    for _ in range(6):
        parent = cur.parent
        if parent is None:
            break
        cur = parent
        txt = cur.get_text(" ", strip=True)
        low = txt.lower()
        if "€" in txt or "m²" in low or "m2" in low:
            return cur
    # repli : deux niveaux au-dessus du lien
    cur = node
    for _ in range(2):
        if cur.parent is not None:
            cur = cur.parent
    return cur


def _first_image(card):
    if not card:
        return None
    for img in card.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        low = src.lower()
        if low.startswith("http") and not any(x in low for x in ("pixel", "spacer", "1x1", "logo", "track", ".gif")):
            return src
    return None


def _first_heading(card):
    if not card:
        return None
    h = card.find(["h1", "h2", "h3", "strong", "b"])
    return _clean_text(h.get_text(" ", strip=True)) if h else None


def _first_group(rx, text):
    m = rx.search(text or "")
    if not m:
        return None
    for g in m.groups():
        if g:
            return g
    return m.group(0)


def _pieces(text):
    m = PIECES_RE.search(text or "")
    if not m:
        return None
    val = m.group(1) or m.group(2)
    return int(val) if val and val.isdigit() else None


def _to_int(num_str):
    digits = re.sub(r"[^\d]", "", num_str or "")
    return int(digits) if digits else None


def _guess_city(text):
    m = CITY_RE.search(text or "")
    if not m:
        return None
    city = _clean_text(m.group(2))
    kept = []
    for w in city.split():
        if w.isupper() and len(w) <= 4:   # coupe les acronymes parasites (DPE, GES, CC...)
            break
        kept.append(w)
    return " ".join(kept) if kept else city


def _guess_type_from_text(text):
    t = (text or "").lower()
    if any(w in t for w in ("à vendre", "a vendre", "vente", "achat", "acheter")):
        return "achat"
    if any(w in t for w in ("à louer", "a louer", "location", "louer", "loyer")):
        return "location"
    return None


def _guess_type_from_price(prix):
    if prix is None:
        return None
    if prix <= 6000:
        return "location"
    if prix >= 20000:
        return "achat"
    return None


def _clean_text(t):
    return re.sub(r"\s+", " ", (t or "").replace(" ", " ")).strip()
