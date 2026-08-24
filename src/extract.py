"""
Extraction des annonces depuis le HTML des mails d'alerte.

Méthode ROBUSTE et indépendante du site : on repère les "cartes" d'annonce par
leur CONTENU (un prix € + une surface m² ou un nombre de pièces), puis on prend
le lien présent dans la carte — même si c'est un lien "traqué" (redirection type
click.by.seloger.com). Ça marche donc pour Leboncoin, SeLoger, Bien'ici, PAP,
Figaro, Jinka… sans connaître la mise en page exacte de chacun.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

# Fragment de domaine (dans l'URL ou l'expéditeur) -> nom lisible de la source.
SOURCE_BY_DOMAIN = {
    "leboncoin": "Leboncoin",
    "seloger": "SeLoger",
    "pap.fr": "PAP",
    "bienici": "Bien'ici",
    "logic-immo": "Logic-Immo",
    "orpi": "Orpi",
    "century21": "Century 21",
    "avendrealouer": "A Vendre A Louer",
    "figaro": "Figaro Immo",
    "ouestfrance-immo": "Ouest-France Immo",
    "superimmo": "SuperImmo",
    "paruvendu": "ParuVendu",
    "immobilier.notaires": "Notaires",
    "jinka": "Jinka",
}

# Liens à ignorer d'office (protocoles, réseaux sociaux, apps).
IGNORE_URL_PARTS = (
    "mailto:", "tel:", "facebook.", "twitter.", "instagram.", "linkedin.",
    "youtube.", "apps.apple.", "play.google.",
)

# Liens à ignorer d'après leur TEXTE (désabo, footer…). Les liens traqués se
# ressemblent tous, donc on filtre sur ce que dit le lien.
IGNORE_LINK_TEXTS = (
    "désabonn", "desabonn", "désinscri", "desinscri", "version en ligne",
    "gérer mes alertes", "gerer mes alertes", "préférence", "preference",
    "mentions légales", "mentions legales", "cookies",
)

PRICE_RE = re.compile(r"([0-9][0-9\s \.]{1,12})\s*€")
SURFACE_RE = re.compile(r"(\d{1,4})(?:[.,]\d{1,2})?\s*m(?:²|2|\^2)", re.I)
PIECES_RE = re.compile(r"(\d{1,2})\s*(?:pi[eè]ces?|p\b)|\b[TF]\s?(\d)\b", re.I)
DPE_RE = re.compile(r"\bDPE\s*[:\-]?\s*([A-G])\b", re.I)
CP_AFTER_RE = re.compile(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]{1,}(?:[ \-][A-Za-zÀ-ÿ'\-]+)?)\s*\(?(\d{5})\)?")
CP_BEFORE_RE = re.compile(r"\b(\d{5})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]+(?:\s[A-Za-zÀ-ÿ'\-]+)?)")


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
    resume: str = ""


def extract_from_email(mail: dict) -> list[Listing]:
    """Point d'entrée : un mail (dict) -> liste d'annonces."""
    html = mail.get("html") or ""
    subject = mail.get("subject") or ""
    sender = mail.get("from") or ""
    default_type = _guess_type_from_text(f"{subject} {sender}")

    if html.strip():
        listings = _extract_from_html(html, subject, sender)
    else:
        listings = _extract_from_text(mail.get("text") or "", subject, sender)

    for lst in listings:
        if lst.type_bien is None:
            lst.type_bien = default_type or _guess_type_from_price(lst.prix)
    return listings


def normalize_url(url: str) -> str:
    """Normalise l'URL pour dédoublonner (on garde la query : les liens traqués en dépendent)."""
    try:
        p = urlparse(url)
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", p.query, ""))
    except Exception:
        return url


# ----------------------------- interne -----------------------------

def _soup(html: str):
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _extract_from_html(html: str, subject: str, sender: str) -> list[Listing]:
    soup = _soup(html)
    listings, seen = [], set()
    for link in soup.find_all("a", href=True):
        url = (link.get("href") or "").strip()
        if _is_junk_link(url, link):
            continue
        card = _listing_card(link)
        if card is None:
            continue
        card_text = _clean_text(card.get_text(" ", strip=True))
        prix = _to_int(_first_group(PRICE_RE, card_text))
        surface = _to_int(_first_group(SURFACE_RE, card_text))
        pieces = _pieces(card_text)
        if prix is None or (surface is None and pieces is None):
            continue                    # pas assez d'infos -> pas une vraie annonce
        ville = _guess_city(card_text)
        sig = (prix, surface, pieces, (ville or "")[:15])
        if sig in seen:
            continue                    # même bien via plusieurs liens de la carte
        seen.add(sig)
        listings.append(Listing(
            source=_source_from_url(url) or _source_from_sender(sender) or "Alerte immo",
            url=url,
            titre=_make_title(card, link, subject, surface, pieces, ville),
            prix=prix, surface=surface, pieces=pieces,
            dpe=_first_group(DPE_RE, card_text),
            image=_first_image(card),
            ville=ville,
            resume=card_text[:400],
        ))
    return listings


def _listing_card(link):
    """Plus petit ancêtre du lien contenant un PRIX + (surface ou pièces)."""
    node = link
    for _ in range(8):
        node = node.parent
        if node is None:
            return None
        txt = node.get_text(" ", strip=True)
        if PRICE_RE.search(txt) and (SURFACE_RE.search(txt) or PIECES_RE.search(txt)):
            return node if len(txt) <= 1600 else None
    return None


def _extract_from_text(text: str, subject: str, sender: str) -> list[Listing]:
    """Repli quand le mail n'a pas de HTML : on cherche des URLs avec un prix à proximité."""
    listings, seen = [], set()
    for m in re.finditer(r"https?://[^\s>\)\"']+", text or ""):
        url = m.group(0)
        if any(b in url.lower() for b in IGNORE_URL_PARTS):
            continue
        window = _clean_text(text[max(0, m.start() - 250): m.end() + 120])
        prix = _to_int(_first_group(PRICE_RE, window))
        surface = _to_int(_first_group(SURFACE_RE, window))
        pieces = _pieces(window)
        if prix is None or (surface is None and pieces is None):
            continue
        sig = (prix, surface, pieces)
        if sig in seen:
            continue
        seen.add(sig)
        listings.append(Listing(
            source=_source_from_url(url) or _source_from_sender(sender) or "Alerte immo",
            url=url, titre=subject, prix=prix, surface=surface, pieces=pieces,
            dpe=_first_group(DPE_RE, window), image=None,
            ville=_guess_city(window), resume=window[:400],
        ))
    return listings


def _is_junk_link(url: str, link) -> bool:
    low = (url or "").lower()
    if not low.startswith("http"):
        return True
    if any(b in low for b in IGNORE_URL_PARTS):
        return True
    txt = (link.get_text(" ", strip=True) or "").lower()
    return any(b in txt for b in IGNORE_LINK_TEXTS)


def _source_from_url(url: str):
    low = (url or "").lower()
    host = (urlparse(url).netloc or "").lower()
    for key, label in SOURCE_BY_DOMAIN.items():
        if key in host or key in low:
            return label
    return None


def _source_from_sender(sender: str):
    low = (sender or "").lower()
    for key, label in SOURCE_BY_DOMAIN.items():
        if key in low:
            return label
    return None


def _make_title(card, link, subject, surface, pieces, ville):
    h = _first_heading(card)
    if h:
        return h
    lt = _clean_text(link.get_text(" ", strip=True))
    if len(lt) >= 8 and not lt.lower().startswith(("voir", "découvrir", "decouvrir")):
        return lt
    bits = []
    if pieces:
        bits.append(f"{pieces} pièces")
    if surface:
        bits.append(f"{surface} m²")
    if ville:
        bits.append(ville)
    return " · ".join(bits) if bits else (subject or "Annonce")


def _first_heading(card):
    if not card:
        return None
    for h in card.find_all(["h1", "h2", "h3", "strong", "b"]):
        t = _clean_text(h.get_text(" ", strip=True))
        if len(t) >= 8 and "€" not in t and re.search(r"[A-Za-zÀ-ÿ]{4,}", t):
            return t
    return None


def _first_image(card):
    if not card:
        return None
    for img in card.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        low = src.lower()
        if low.startswith("http") and not any(x in low for x in ("pixel", "spacer", "1x1", "logo", "track", ".gif")):
            return src
    return None


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
    m = CP_BEFORE_RE.search(text or "")     # "77100 Meaux" / "69003 Lyon" (prioritaire)
    if m:
        return _trim_city(m.group(2))
    m = CP_AFTER_RE.search(text or "")      # "Meaux (77100)"
    if m:
        return _trim_city(m.group(1))
    return None


def _trim_city(city):
    city = _clean_text(city)
    kept = []
    for w in city.split():
        if w.isupper() and len(w) <= 4:     # coupe les acronymes parasites (DPE, GES, CC…)
            break
        kept.append(w)
    return " ".join(kept) if kept else city


def _guess_type_from_text(text):
    t = (text or "").lower()
    if any(w in t for w in ("à vendre", "a vendre", "vente", "achat", "acheter")):
        return "achat"
    if any(w in t for w in ("à louer", "a louer", "location", "louer", "loyer", "/mois")):
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
    return re.sub(r"\s+", " ", t or "").strip()
