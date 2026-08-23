"""
Lecture de la boîte Gmail par IMAP.

Principe d'état SANS base de données :
  - un mail NON LU  = pas encore traité
  - un mail LU      = déjà traité
On lit donc les non-lus, on les traite, puis on les marque "lus".
On utilise BODY.PEEK pour NE PAS marquer un mail lu juste en le lisant.
"""

import email
import imaplib
from email.header import decode_header, make_header
from email.message import Message


def connect(host: str, user: str, password: str) -> imaplib.IMAP4_SSL:
    """Se connecte à Gmail (IMAP sécurisé) et sélectionne la boîte de réception."""
    imap = imaplib.IMAP4_SSL(host)
    imap.login(user, password)
    imap.select("INBOX")
    return imap


def fetch_unread(imap: imaplib.IMAP4_SSL) -> list[dict]:
    """
    Récupère les mails NON LUS sans les marquer lus.
    Renvoie une liste de dicts : {uid, from, subject, html, text}.
    """
    typ, data = imap.uid("search", None, "UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return []

    mails = []
    for uid in data[0].split():
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        html, text = _get_bodies(msg)
        mails.append({
            "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
            "from": _decode(msg.get("From", "")),
            "subject": _decode(msg.get("Subject", "")),
            "html": html,
            "text": text,
        })
    return mails


def mark_read(imap: imaplib.IMAP4_SSL, uid: str) -> None:
    """Marque un mail comme lu (pour ne pas le retraiter au prochain passage)."""
    imap.uid("store", uid, "+FLAGS", "(\\Seen)")


def logout(imap: imaplib.IMAP4_SSL) -> None:
    """Ferme proprement la connexion."""
    for action in (imap.close, imap.logout):
        try:
            action()
        except Exception:
            pass


# ----------------------------- interne -----------------------------

def _decode(value: str) -> str:
    """Décode un en-tête (sujet, expéditeur) potentiellement encodé (=?utf-8?...)."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _get_bodies(msg: Message) -> tuple[str, str]:
    """Renvoie (html, texte) en parcourant les parties du mail."""
    html_parts, text_parts = [], []
    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition") or ""):
                continue
            ctype = part.get_content_type()
            if ctype == "text/html":
                html_parts.append(_payload_to_str(part))
            elif ctype == "text/plain":
                text_parts.append(_payload_to_str(part))
    else:
        if msg.get_content_type() == "text/html":
            html_parts.append(_payload_to_str(msg))
        else:
            text_parts.append(_payload_to_str(msg))
    return "\n".join(html_parts), "\n".join(text_parts)


def _payload_to_str(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")
