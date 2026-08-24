# Design — Dashboard immo perso « Jinka+ » (Phase 2)

**Date :** 2026-08-24
**Statut :** design approuvé (cadre) — Tranche 0 (spike Jinka) à valider avant plan détaillé.

## Contexte
La Phase 1 (bot alertes-mail + IA + Discord, dans `E:\immo-bot`) fonctionne comme socle.
La Phase 2 vise un **vrai produit perso** : une app sur l'écran d'accueil de l'iPhone qui
affiche les annonces, laisse régler les critères, ouvrir/mettre en favoris, et **notifie en push**
quand un bien colle — le tout **100 % gratuit**, avec **Jinka comme source** (il agrège déjà tous
les sites) et **notre couche** d'intelligence par-dessus.

## Décisions verrouillées (issues du brainstorming)
- **Interface** : **PWA** (page web ajoutée à l'écran d'accueil → icône plein écran). Pas de widget natif (App Store payant), pas de widget Scriptable.
- **Notifications** : **Web Push natif iOS** (iOS 16.4+, PWA installée). Choisi plutôt que Discord.
- **Source de données** : **Façon B** = lire le compte Jinka de l'utilisateur via l'API de son appli (non officielle). **Filet** si Jinka bloque : alertes Jinka en e-mail invisible → même app derrière.
- **Gratuité** : 0 € partout, aucune carte bancaire.
- **Zone / perso** : recherche autour de Disneyland Paris (Chessy, 77) ; coords travail ~48.878, 2.780.

## Architecture (gratuite)
```
  Jinka (compte user) ──API──▶ Collecteur (Python / GitHub Actions ← réutilise Phase 1)
                                  │  IA (Gemini) : note + message ; enrichissement
                                  ▼
                            Supabase (Postgres gratuit)
                              ▲                  │
                     lit/écrit│                  │ envoie
   PWA (app iPhone) ──────────┘                  └──▶ Web Push iOS (gratuit)
   annonces · critères · favoris · statut
```

## Composants (unités isolées)
- **Collecteur** (`Python`, GitHub Actions, cron) : lit Jinka → dédoublonne → note via IA (réutilise `src/score.py`) → écrit en base → déclenche les push pour les nouveautés qui passent le seuil. Dépend de : token Jinka, Supabase, clé Gemini, clés VAPID.
- **Base Supabase** : stockage partagé collecteur ↔ app. Tables (esquisse) :
  - `listings` : id, source, ext_id, titre, url, prix, surface, pieces, ville, cp, dpe, image, type_bien, lat, lng, first_seen, last_seen.
  - `criteria` : budget_max, surface_min, pieces_min, zones[], wishlist, seuil, transport, work_lat, work_lng (1 ligne, perso).
  - `scores` : listing_id, note, raisons[], message_contact, (plus tard) travel_min, prix_vs_marche.
  - `favorites` : listing_id, statut (a_contacter/contacte/visite/refuse), note_perso, added_at.
  - `push_subscriptions` : endpoint, keys, created_at.
- **PWA** (statique, Cloudflare Pages) : liste triée par note, filtres, détail, bouton favori + statut, formulaire critères (écrit dans `criteria`), enregistrement au Web Push. Manifest + service worker + icône pour « Ajouter à l'écran d'accueil ».
- **Web Push** : clés VAPID ; la PWA s'abonne (stocke la subscription en base) ; le collecteur envoie les push via `pywebpush`.

## Découpage en tranches (dé-risque d'abord)
- **Tranche 0 — Spike Jinka** *(critique, incertain)* : prouver qu'on peut récupérer les annonces du compte Jinka par programme (repérer l'endpoint + l'auth, capturer un token, tester un `fetch`). Résultat : GO (Façon B) ou repli (Jinka par e-mail invisible). Rien d'autre n'est construit avant.
- **Tranche 1 — MVP app** : collecteur Jinka → Supabase ; PWA (liste + critères + favoris + clic). Pas de push.
- **Tranche 2 — Web Push** : abonnement + envoi ; installable et notifie sur iPhone.
- **Tranche 3 — Intelligence** : temps de trajet réel vers Disneyland (géocodage BAN gratuit + routage) ; prix vs marché (DVF) ; DPE.

## Risques & parades
- **Façon B fragile / non officielle** : l'API Jinka peut changer ou exiger une ré-auth (token qui expire, protection anti-bot au login). Parade : capturer un token long, gérer l'expiration, et **repli e-mail** si ça casse. → C'est précisément l'objet de la Tranche 0.
- **Push iOS** : ne marche que PWA installée (écran d'accueil) + iOS 16.4+. Parade : Discord en secours si besoin.
- **Gratuité** : rester dans les paliers gratuits (Supabase, GitHub Actions public, Gemini, Cloudflare). Cap sur le volume d'annonces traitées par run si nécessaire.

## Critères de succès (MVP)
1. Une annonce apparue chez Jinka se retrouve dans la base puis dans l'app en < ~30 min.
2. L'app s'installe sur l'écran d'accueil iPhone et affiche les annonces triées par note.
3. On peut régler ses critères depuis l'app, mettre en favori et rouvrir la liste des favoris.
4. Un clic sur une annonce ouvre la vraie annonce.
5. (Tranche 2) Une notif push arrive sur l'iPhone pour une nouvelle pépite.
6. Tout reste à 0 €.

## Tranche 0 — RÉSULTAT : ✅ VALIDÉE (2026-08-24)
API `https://api.jinka.fr/apiv2`, auth par **token JWT** (`JINKA_ACCESS_TOKEN` ; compte email+code sans
mot de passe → token extrait du navigateur, peut expirer). Endpoints : `GET /apiv2/alert` puis
`GET /apiv2/alert/{id}/dashboard`. **Jinka accepte l'IP de GitHub Actions** → collecteur 24/7 gratuit OK.
Schéma annonce confirmé : `id, uuid, external_id, reference, rent, rent_max, fees, area, room, bedroom,
floor, energy_dpe, energy_ges, lat, lng, quartier, city, stops, images, features, furnished, is_coliving,
type, favorite`. Script = `jinka_test.py` + workflow `jinka-test`.
À résoudre en Tranche 1 : l'**URL de clic** vers l'annonce (via endpoint `alert_result_view_ad` ou build).

## Prochaine étape
Setup : **GitHub Desktop** (fin du copier-coller) + projet **Supabase**. Puis construire la **Tranche 1**
(collecteur Jinka → Supabase + PWA).
