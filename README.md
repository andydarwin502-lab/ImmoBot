# 🏠 Bot immo perso — « Alertes + IA »

Un petit robot **100 % gratuit** qui repère des annonces (location **et** achat) sur les
sites immo, ne garde **que celles qui te correspondent vraiment** grâce à une IA, et te les
envoie sur **Discord** — avec un message de contact prêt à copier-coller.

> 👉 **Tu débutes ? Suis le guide pas-à-pas : [TUTO.md](TUTO.md).** Tout y est expliqué.

## Comment ça marche

```
Sites immo + Jinka  ──(alertes e-mail)──▶  Gmail dédié
                                              │
        GitHub Actions (toutes les ~15 min)   ▼
   1. lit les nouveaux mails      4. IA Gemini : note /100 + rédige un message
   2. extrait les annonces        5. envoie les pépites sur Discord
   3. filtres de base (prix…)     6. marque les mails comme lus
```

Aucun scraping, aucun serveur à payer, aucune carte bancaire. Le tout tient avec :
**Gmail** (gratuit) + **Gemini** (IA, palier gratuit) + **Discord** (webhook) + **GitHub Actions**.

## Tester sur ton PC (facultatif)

```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py --fixtures --dry-run
```

- `--fixtures` : utilise les faux mails de `tests/fixtures/` (aucune connexion nécessaire).
- `--dry-run` : affiche le résultat au lieu d'envoyer sur Discord.
- Pour un test réel en local, copie `.env.example` en `.env`, remplis-le, puis :
  `.venv\Scripts\python main.py --once --dry-run`

## Structure

| Fichier | Rôle |
|---|---|
| `config/criteria.yml` | **Tes critères** (le seul fichier à éditer au quotidien) |
| `main.py` | Orchestrateur |
| `src/mailbox.py` | Lecture des mails (IMAP) |
| `src/extract.py` | Extraction des annonces depuis les mails |
| `src/score.py` | Notation par l'IA (Gemini) |
| `src/notify.py` | Envoi Discord |
| `.github/workflows/run.yml` | Le déclencheur automatique (toutes les 15 min) |
| `TUTO.md` | Le guide complet pour débutant |

## Limites (à connaître)

- Couvre les sites qui **envoient des alertes e-mail** (l'essentiel du marché + Jinka), pas
  littéralement « tous les sites ».
- GitHub peut lancer le bot avec **quelques minutes de retard** aux heures de pointe.
- Le contact est **semi-automatique** (le bot rédige, tu copies-colles) — volontaire, pour ne
  pas te faire bannir des sites.
