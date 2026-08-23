"""Dédoublonnage des annonces d'un même passage (par URL normalisée)."""

from src.extract import normalize_url


def dedupe(listings: list) -> list:
    seen, out = set(), []
    for lst in listings:
        key = normalize_url(lst.url) if lst.url else id(lst)
        if key in seen:
            continue
        seen.add(key)
        out.append(lst)
    return out
