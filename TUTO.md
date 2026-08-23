# 📖 Le guide complet (pour débutant) — ton bot immo, pas à pas

Salut ! Ce guide te fait installer ton bot **du début à la fin**, sans rien connaître au code.
Prends ton temps, coche chaque étape (✅) au fur et à mesure. Compte **45 min à 1 h** la première fois.

**Tu n'as besoin d'aucune carte bancaire. Tout est gratuit.**

---

## 🧭 Ce que fait le bot (et ce qu'il ne fait pas)

**Il fait :** il surveille les mails d'alerte que les sites immo t'envoient, garde **seulement**
les annonces qui collent à tes critères (grâce à une IA), et te les envoie sur **Discord** avec
un message de contact déjà rédigé.

**Il ne fait pas :** il ne « scanne » pas internet tout seul (il s'appuie sur les alertes des
sites) et il **n'envoie pas** les messages à ta place (tu copies-colles — c'est volontaire, pour
éviter de te faire bannir des sites).

**Les 5 ingrédients (tous gratuits) :**
1. 📥 une adresse **Gmail** dédiée (reçoit les alertes)
2. 🧠 une clé **Gemini** (l'IA qui trie)
3. 🤖 un **webhook Discord** (reçoit les pépites)
4. 🐙 un compte **GitHub** (fait tourner le bot 24/7)
5. ⚙️ ce projet (le code, déjà prêt)

---

## Étape 1 — Créer l'adresse Gmail dédiée 📥

> Pourquoi une adresse **dédiée** ? Pour que les alertes immo n'encombrent pas ta boîte perso,
> et parce que le bot va lire cette boîte : autant qu'elle ne contienne QUE ça.

1. ✅ Va sur **https://accounts.google.com/signup** et crée une nouvelle adresse
   (ex : `tarecherche.immo.2026@gmail.com`).
2. ✅ Une fois connecté, active la **validation en 2 étapes** (obligatoire pour l'étape suivante) :
   - Va sur **https://myaccount.google.com/security**
   - Section « Validation en deux étapes » → clique et suis les instructions (il faudra ton
     numéro de téléphone).

### 1.b — Générer un « mot de passe d'application » 🔑 (le piège classique !)

Le bot ne peut pas utiliser ton mot de passe Gmail normal. Il lui faut un **mot de passe
d'application** (un code spécial de 16 lettres).

1. ✅ Va sur **https://myaccount.google.com/apppasswords**
   *(si la page dit que ce n'est pas disponible : c'est que la validation en 2 étapes de
   l'étape 1 n'est pas encore activée — reviens l'activer.)*
2. ✅ Dans « Nom de l'application », tape `bot immo` puis clique **Créer**.
3. ✅ Google affiche un code du type `abcd efgh ijkl mnop`. **Copie-le et garde-le** de côté
   (bloc-notes). C'est ton `GMAIL_APP_PASSWORD`. Les espaces n'ont pas d'importance.

---

## Étape 2 — Créer tes alertes sur les sites immo 🔔

Le principe : sur chaque site, tu crées une **alerte e-mail** réglée **LARGE** (juste la ville
et le budget max). C'est **l'IA** qui affinera ensuite — donc ne mets pas trop de critères ici,
sinon tu risques de rater des biens.

Sur chaque site : **inscris-toi avec ton Gmail dédié**, fais une recherche (ta ville + ton budget),
puis clique sur **« Enregistrer la recherche »** / **« Créer une alerte »** et choisis de recevoir
les nouvelles annonces **par e-mail** (idéalement « en temps réel » / « immédiat »).

Sites recommandés (fais ceux qui t'intéressent) :
- ✅ **Leboncoin** — https://www.leboncoin.fr
- ✅ **SeLoger** — https://www.seloger.com
- ✅ **PAP** (particuliers) — https://www.pap.fr
- ✅ **Bien'ici** — https://www.bienici.com
- ✅ **Logic-Immo** — https://www.logic-immo.com
- ✅ **Jinka** (agrégateur) — https://www.jinka.fr — pratique car il regroupe déjà plein de sites.

> 💡 Astuce : commence par **2-3 sites** (Leboncoin + SeLoger + Jinka par exemple). Tu en
> ajouteras d'autres plus tard. Vérifie dans ton Gmail dédié que tu **reçois bien** les premiers
> mails d'alerte avant de continuer.

---

## Étape 3 — Créer le salon Discord + le webhook 🤖

Le **webhook**, c'est juste une « adresse » secrète vers laquelle le bot envoie les annonces.

1. ✅ Installe/ouvre **Discord** (https://discord.com) et connecte-toi (compte gratuit).
2. ✅ Crée un serveur : bouton **+** à gauche → **Créer mon propre serveur** → « Pour moi ».
3. ✅ Tu as un salon `#général`. Passe la souris dessus → **roue crantée** (Modifier le salon).
4. ✅ Onglet **Intégrations** → **Webhooks** → **Nouveau webhook**.
5. ✅ Donne-lui un nom (« Bot immo »), puis clique **Copier l'URL du webhook**.
   Garde cette URL de côté : c'est ton `DISCORD_WEBHOOK_URL`
   (ça ressemble à `https://discord.com/api/webhooks/123.../abc...`).

> 📱 Installe aussi Discord sur ton téléphone et active les notifications du salon : comme ça tu
> es prévenu **instantanément** quand une pépite tombe.

---

## Étape 4 — Obtenir la clé IA Gemini (gratuite) 🧠

1. ✅ Va sur **https://aistudio.google.com/apikey** (connecte-toi avec un compte Google — tu
   peux réutiliser ton Gmail dédié).
2. ✅ Clique **« Create API key »** (Créer une clé API). Accepte les conditions si demandé.
3. ✅ Copie la clé (elle commence par `AIza...`). C'est ton `GEMINI_API_KEY`.

> 💳 Aucune carte bancaire demandée. Le palier gratuit suffit très largement pour un usage perso.

---

## Étape 5 — Mettre le projet sur GitHub 🐙

GitHub va **héberger et faire tourner** ton bot gratuitement, 24 h/24, même PC éteint.

### 5.a — Créer ton compte
✅ Va sur **https://github.com/signup** et crée un compte gratuit.

### 5.b — Envoyer le projet (méthode simple, sans ligne de commande)

Le plus simple est **GitHub Desktop** (une appli avec des boutons, pas de code) :

1. ✅ Télécharge et installe **GitHub Desktop** : https://desktop.github.com (gratuit).
2. ✅ Ouvre-le, connecte-toi avec ton compte GitHub.
3. ✅ Menu **File → Add local repository…** puis choisis le dossier `E:\immo-bot`.
   - S'il propose « create a repository », accepte (**Create a repository**).
4. ✅ Clique **Publish repository**.
   - ⚠️ **Décoche** « Keep this code private » → laisse le dépôt **public**.
     *(Pourquoi public ? Pour que GitHub fasse tourner le bot en **illimité et gratuit**. Rassure-toi :
     tes mots de passe/clés ne sont PAS dans le code — on les met à part à l'étape 6. Seuls tes
     critères de recherche seraient visibles. Si tu préfères vraiment un dépôt privé, garde-le
     privé mais règle la fréquence sur « toutes les heures » à l'étape 9 pour rester gratuit.)*
   - Clique **Publish repository**.

✅ Ton code est maintenant sur GitHub ! (GitHub Desktop ignore automatiquement `.venv` et `.env`.)

> **Sans GitHub Desktop ?** Sur https://github.com/new, crée un dépôt public `immo-bot`, puis
> **Add file → Upload files**, et glisse tout le contenu du dossier `E:\immo-bot` **SAUF** les
> dossiers `.venv` et `__pycache__` et le fichier `.env` s'il existe. Valide avec **Commit changes**.

---

## Étape 6 — Coller tes 4 secrets dans GitHub 🔒

C'est ici qu'on range tes mots de passe/clés, **au chaud et chiffrés** (invisibles, même sur un
dépôt public).

1. ✅ Sur la page de ton dépôt GitHub, va dans **Settings** (onglet en haut).
2. ✅ Menu de gauche : **Secrets and variables → Actions**.
3. ✅ Bouton **New repository secret**. Crée ces **4** secrets, un par un (respecte les noms
   **EXACTEMENT**, tout en majuscules) :

| Name (nom exact) | Secret (valeur) |
|---|---|
| `GMAIL_USER` | ton adresse Gmail dédiée (ex : `tarecherche.immo.2026@gmail.com`) |
| `GMAIL_APP_PASSWORD` | le mot de passe d'application (étape 1.b) |
| `GEMINI_API_KEY` | la clé `AIza...` (étape 4) |
| `DISCORD_WEBHOOK_URL` | l'URL du webhook (étape 3) |

> ✅ Pour chacun : tape le **Name**, colle la **valeur**, clique **Add secret**. Recommence 4 fois.

---

## Étape 7 — Régler tes critères 🎯

C'est le fichier qui décide ce que le bot te remonte.

1. ✅ Sur GitHub, ouvre le dossier `config` puis le fichier **`criteria.yml`**.
2. ✅ Clique sur l'icône **crayon** (✏️ « Edit this file »).
3. ✅ Modifie :
   - `budget_max`, `surface_min`, `pieces_min` : tes filtres chiffrés.
   - `villes:` : ta/tes ville(s) (garde le tiret `-` et les guillemets).
   - `wishlist:` : **le plus important** — décris en français ce que tu aimes / ce que tu fuis.
     Plus tu es précis, meilleur est le tri. (Ex : « lumineux, pas de rez-de-chaussée, proche
     tram, vraies photos, calme ; je fuis les DPE F/G et les rues bruyantes ».)
   - `seuil_note:` : 70 par défaut. Baisse à 60 si tu reçois trop peu, monte à 80 si trop.
   - Pour l'achat : passe `actif: false` à `actif: true` sous `achat:` si tu veux l'activer.
4. ✅ En bas : **Commit changes**.

> ⚠️ Respecte l'**indentation** (les espaces en début de ligne). Ne mets pas de tabulation.

---

## Étape 8 — Lancer et vérifier ✅

1. ✅ Sur GitHub, onglet **Actions** (en haut). Si un bandeau demande d'autoriser les workflows,
   clique **« I understand my workflows, go ahead and enable them »**.
2. ✅ À gauche, clique le workflow **immo-bot** → bouton **Run workflow** (à droite) → **Run workflow**.
3. ✅ Attends ~1 min, rafraîchis. Clique sur le run pour voir le déroulé. Tu dois voir des lignes
   comme `📥 X nouveau(x) mail(s)` puis `⭐ X pépite(s)`.
4. ✅ **Regarde ton Discord** : les pépites doivent apparaître ! 🎉

> Rien sur Discord ? Ce n'est pas forcément un bug : peut-être qu'aucune annonce n'a passé le
> seuil, ou qu'il n'y avait aucun mail non lu. Va voir la section **Dépannage** ci-dessous.

À partir de là, **c'est automatique** : le bot tourne tout seul toutes les ~15 minutes.

---

## Étape 9 — Régler la fréquence ⏰ (facultatif)

1. Ouvre `.github/workflows/run.yml` sur GitHub → crayon ✏️.
2. Trouve la ligne `- cron: "*/15 * * * *"` :
   - `*/15` = toutes les 15 min (défaut, idéal location).
   - `*/30` = toutes les 30 min.
   - `0 * * * *` = toutes les heures (conseillé si ton dépôt est **privé**, pour rester gratuit).
3. **Commit changes**.

---

## 🛠️ Dépannage (les cas les plus fréquents)

**« Rien n'arrive sur Discord »**
- Vérifie que ton **Gmail dédié reçoit bien** des mails d'alerte (étape 2). Pas de mail = rien à traiter.
- Le bot ne lit que les mails **non lus**. Si tu as ouvert les mails toi-même, il les ignore.
- Le seuil est peut-être trop haut : baisse `seuil_note` à 60 dans `criteria.yml`.

**Le run est rouge (échec) dans l'onglet Actions**
- Clique le run → lis la dernière ligne rouge.
- `GMAIL_USER / GMAIL_APP_PASSWORD manquants` → un secret est mal nommé (étape 6). Vérifie
  l'orthographe EXACTE des 4 noms.
- Erreur de connexion Gmail → tu as mis ton mot de passe **normal** au lieu du **mot de passe
  d'application** (refais l'étape 1.b).

**« invalid credentials » / login Gmail refusé**
- Régénère un mot de passe d'application (étape 1.b) et recolle-le dans le secret `GMAIL_APP_PASSWORD`.

**Erreur liée à Gemini / quota**
- Le palier gratuit a des limites journalières. Si tu reçois des centaines d'annonces/jour,
  resserre tes alertes (étape 2) ou tes filtres (`budget_max`, `surface_min`).
- Vérifie que `GEMINI_API_KEY` est bien collée (elle commence par `AIza`).

**Le bot s'est arrêté après ~2 mois**
- Normal si le dépôt est resté sans activité : GitHub met en pause les tâches programmées après
  60 jours. Le workflow **keepalive** est là pour éviter ça tout seul ; si besoin, va dans
  **Actions → immo-bot → Run workflow** pour le relancer.

**Une annonce mal lue (prix/surface faux)**
- L'extraction depuis les mails est « au mieux ». Si un site change son format, dis-le moi et
  on ajuste `src/extract.py` — ça n'affecte que ce site.

---

## 🎉 Voilà !

Ton bot tourne. Tu peux à tout moment revenir modifier `config/criteria.yml` sur GitHub pour
affiner ce qu'il te remonte. Bonne chasse à l'appartement ! 🏠
