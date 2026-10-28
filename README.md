# DatAtlaSonore

Une alternative perso à Last.fm : l'app enregistre **toutes** tes écoutes Deezer, y compris celles que le scrobbling rate, et en tire des statistiques. Tu y trouveras tes tops artistes, albums, titres et genres, l'évolution dans le temps, tes habitudes d'écoute, tes découvertes, un récap du jour, de la semaine, du mois ou de l'année, l'historique complet et des extraits de 30 s.

- **Phase 1 (local)** : l'app tourne sur ton ordinateur, dans ton navigateur.
- **Phase 2 (en ligne, gratuit)** : un robot GitHub relève tes écoutes toutes les 30 minutes, même ordinateur éteint, et les range dans un fichier SQLite publié dans le dépôt GitHub (branche `data`). L'app est publiée sur Streamlit Community Cloud.

Passer de la phase 1 à la phase 2 ne demande **que de la configuration** : le code est le même.

```
          ┌──────────────────────┐   cookie arl    ┌──────────────────────┐
          │ scripts/sync.py      │ ──────────────► │ API interne Deezer   │
          │ (ton Mac, ou GitHub  │                 └──────────────────────┘
          │  Actions /30 min)    │ ──► api.deezer.com (pochettes, genres)
          └─────────┬────────────┘ ──► MusicBrainz (tags de genres)
                    │ écrit
                    ▼
          ┌──────────────────────┐
          │ Base de données      │  SQLite, partagée via la branche `data` du dépôt
          └─────────┬────────────┘
                    │ lit seulement
                    ▼
          ┌──────────────────────┐
          │ App Streamlit        │  ne connaît PAS le cookie arl
          └──────────────────────┘
```

> ⚠️ **Tant que tu es en phase 1, tes écoutes ne sont relevées que quand ton ordinateur est allumé** et que la synchro tourne. Deezer ne garde que tes **100 dernières écoutes** : si tu en fais plus de 100 entre deux synchros, les plus anciennes sont perdues. **Active la phase 2 (étapes 5 et 6) le plus tôt possible** pour ne rien perdre.

---

## Sommaire

1. [Installer Python et l'environnement](#1-installer-python-et-lenvironnement)
2. [Récupérer ton cookie `arl`](#2-récupérer-ton-cookie-arl)
3. [Première synchro, puis l'app en local](#3-première-synchro-puis-lapp-en-local)
4. [(Optionnel) Planifier la synchro en local](#4-optionnel-planifier-la-synchro-en-local)
5. [Passer en ligne : la synchro sur GitHub](#5-passer-en-ligne--la-synchro-sur-github-même-ordinateur-éteint)
6. [Publier l'app sur Streamlit Community Cloud](#6-publier-lapp-sur-streamlit-community-cloud)
7. [En cas de problème](#7-en-cas-de-problème)
8. [Excel, albums & playlists, affiche A3](#excel-albums--playlists-affiche-a3)
9. [Récupérer l'historique plus ancien (export Deezer)](#récupérer-lhistorique-plus-ancien-export-deezer)
10. [Limites connues](#limites-connues)

Les commandes sont à taper dans un **terminal** :
- **macOS** : app « Terminal » (Cmd + Espace, puis tape « Terminal »).
- **Windows** : « PowerShell » (menu Démarrer, puis tape « PowerShell »).

Tape une commande, puis Entrée. Copie-les telles quelles.

---

## 1. Installer Python et l'environnement

### 1.1 Installer Python 3.12

Télécharge **Python 3.12** sur <https://www.python.org/downloads/> et installe-le.
- **Windows** : sur le premier écran de l'installeur, coche **« Add python.exe to PATH »**.

Vérifie l'installation :

| macOS | Windows |
|---|---|
| `python3.12 --version` | `py -3.12 --version` |

Le terminal doit afficher `Python 3.12.x`.

### 1.2 Aller dans le dossier du projet

| macOS | Windows |
|---|---|
| `cd "$HOME/Library/CloudStorage/OneDrive-Personnel/06 MUSIQUE/01 Projet Webapp/Code LastFM Bis"` | `cd "$HOME\OneDrive\06 MUSIQUE\01 Projet Webapp\Code LastFM Bis"` |

Adapte le chemin s'il est différent chez toi. Les guillemets sont nécessaires à cause des espaces.

### 1.3 Créer l'environnement virtuel et installer les dépendances

C'est une « boîte » isolée qui contient les bibliothèques du projet. Elle ne touche pas au reste de ton ordinateur.

**macOS**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> Si Windows refuse d'exécuter `Activate.ps1`, lance une fois `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, réponds `O`, puis recommence.

Quand l'environnement est actif, `(.venv)` apparaît au début de la ligne du terminal. **À chaque nouveau terminal**, refais `cd …` (1.2) puis la ligne `source …` (macOS) ou `.venv\Scripts\Activate.ps1` (Windows).

> 💡 Le dossier est dans OneDrive : OneDrive va synchroniser les milliers de petits fichiers de `.venv`. Ce n'est pas grave, mais tu peux faire un clic droit sur `.venv` > « Libérer de l'espace » ou l'exclure de la synchro.

---

## 2. Récupérer ton cookie `arl`

Le cookie `arl` est la « clé de session » de ton compte Deezer dans le navigateur. Le script l'utilise pour lire ton historique d'écoute.

> 🔐 **Ce cookie donne un accès complet à ton compte Deezer**, comme ton mot de passe. Ne l'envoie à personne, ne le colle pas dans un message, ne le mets jamais dans GitHub en dehors des « Secrets ». L'app web ne le connaît pas : seul le script de synchro l'utilise.

### Où le trouver (Chrome, Edge ou Brave)

1. Va sur <https://www.deezer.com> et connecte-toi.
2. Ouvre les outils de développement : **Cmd + Option + I** (macOS) ou **F12** (Windows).
3. Clique sur l'onglet **Application**. S'il n'apparaît pas, clique sur `»`.
4. À gauche : **Storage > Cookies > https://www.deezer.com**.
5. Dans la liste, trouve la ligne **`arl`** et double-clique sur sa **Value** (une longue suite de chiffres et de lettres). Copie-la.

Sur **Firefox**, c'est l'onglet **Stockage > Cookies**. Sur **Safari**, active d'abord le menu Développement (Réglages > Avancés > « Afficher les fonctionnalités pour les développeurs web »), puis **Stockage > Cookies**.

### Le mettre dans le fichier `.env`

1. Copie le modèle :

   | macOS | Windows |
   |---|---|
   | `cp .env.example .env` | `Copy-Item .env.example .env` |

2. Ouvre `.env` avec un éditeur de texte (TextEdit, Bloc-notes, VS Code…) et remplis-le :
   ```
   DEEZER_ARL=la_longue_valeur_copiée
   ADMIN_PASSWORD=un_mot_de_passe_pour_la_page_corrections
   ```
3. Enregistre. Le fichier `.env` est ignoré par git : il ne partira jamais sur GitHub.

### Si ton compte a plusieurs profils (offre Family)

Chaque profil Deezer a **son propre historique**, et le cookie ouvre toujours le profil principal. Pour suivre un autre profil, indique son nom dans `.env` :

```
DEEZER_PROFILE=TBTC
```

La synchro bascule alors sur ce profil, comme le fait le site quand tu changes de profil. Pour voir la liste des profils du compte : `python -m scripts.diagnose_deezer`.

---

## 3. Première synchro, puis l'app en local

### 3.1 Synchroniser

```bash
python -m scripts.sync
```

Tu dois voir à la fin : `OK: 100 plays fetched, 100 new.`. Tes écoutes sont enregistrées dans `data/deezer_stats.db`.

La synchro complète aussi les métadonnées (pochettes, labels, genres Deezer et MusicBrainz) pendant au plus 2 minutes, puis s'arrête. Le reste est fait aux synchros suivantes. Pour tout enrichir d'un coup :

```bash
python -m scripts.sync --enrich-only --enrich-budget 900
```

### 3.2 Lancer l'app

Le plus simple : double-clique sur **« Lancer l'app.command »** (et **« Arrêter l'app.command »** pour l'arrêter). En ligne de commande :

```bash
python -m scripts.dev_server --port 8501
```

Ton navigateur s'ouvre sur <http://localhost:8501>. Pour arrêter l'app : **Ctrl + C** dans le terminal.

Tu n'as **jamais besoin de relancer l'app** après une modification :
- code (`app/`, `core/`) : la page ouverte se met à jour toute seule en 2 à 3 secondes ; une sauvegarde à moitié finie affiche l'erreur, la sauvegarde suivante la répare (`app/devreload.py`) ;
- réglages (`.streamlit/config.toml`, `.env`, `requirements.txt`) : le superviseur redémarre l'app et la page se reconnecte d'elle-même (`scripts/dev_server.py`) ;
- plantage : le superviseur relance l'app automatiquement.

L'app s'organise autour d'un rail à gauche (Accueil, Classements, Rythmes, Découvertes, Pour toi, Univers, Récaps, Bibliothèque, Journal, Réglages) et d'une recherche en haut qui ouvre la fiche d'un artiste, d'un album ou d'un titre. La période se choisit dans l'en-tête de chaque page et reste la même d'une page à l'autre.

### 3.3 (Optionnel) Essayer l'app avec des données fictives

Utile pour explorer l'app sans attendre d'avoir beaucoup d'écoutes. Les écoutes de démonstration sont rangées dans une base séparée, `data/demo.db` :

**macOS**
```bash
python -m scripts.seed_demo
DATABASE_URL=sqlite:///data/demo.db streamlit run app/Home.py
```

**Windows (PowerShell)**
```powershell
python -m scripts.seed_demo
$env:DATABASE_URL="sqlite:///data/demo.db"; streamlit run app/Home.py
```

Sous Windows, ferme ensuite le terminal pour revenir à ta vraie base.

### 3.4 Lancer les tests (optionnel)

```bash
pytest
```

---

## 4. (Optionnel) Planifier la synchro en local

**Le plus simple (macOS)** : double-clique sur **`Activer la synchro automatique.command`**.
- La synchro tourne alors toutes les 30 minutes en arrière-plan, même app fermée, tant que le Mac est allumé.
- Après une mise en veille, la synchro manquée est rattrapée au réveil.
- Le journal de la synchro est dans `logs/autosync.log`.
- Pour arrêter : `Désactiver la synchro automatique.command`.

> ⚠️ Si le Mac reste éteint plus d'une journée pendant que tu écoutes beaucoup, des écoutes peuvent être perdues : Deezer ne garde que les 100 dernières. Pour ne rien perdre, même ordinateur éteint pendant un mois, il faut la synchro en ligne (étape 5).

Les instructions manuelles ci-dessous restent valables (Windows, ou réglages personnalisés).

Pour lancer la synchro toutes les 30 minutes, quand l'ordinateur est allumé. **La phase 2 est plus fiable** : si tu comptes la mettre en place bientôt, passe directement à l'étape 5.

### macOS (launchd)

1. Crée le fichier `~/Library/LaunchAgents/com.deezerstats.sync.plist` avec ce contenu. **Adapte les deux chemins** si ton dossier n'est pas au même endroit, et remplace `TON_NOM` par ton nom d'utilisateur macOS. Pour le connaître, tape `whoami` dans le terminal.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.deezerstats.sync</string>
  <key>WorkingDirectory</key>
  <string>/Users/TON_NOM/Library/CloudStorage/OneDrive-Personnel/06 MUSIQUE/01 Projet Webapp/Code LastFM Bis</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/TON_NOM/Library/CloudStorage/OneDrive-Personnel/06 MUSIQUE/01 Projet Webapp/Code LastFM Bis/.venv/bin/python</string>
    <string>-m</string><string>scripts.sync</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/deezerstats-sync.log</string>
  <key>StandardErrorPath</key><string>/tmp/deezerstats-sync.log</string>
</dict>
</plist>
```

2. Active-la :
   ```bash
   launchctl load ~/Library/LaunchAgents/com.deezerstats.sync.plist
   ```
3. Vérifie au bout d'une minute : `cat /tmp/deezerstats-sync.log`.

   Si le journal contient « Operation not permitted », macOS bloque l'accès au dossier OneDrive. Ouvre Réglages Système > Confidentialité et sécurité > Accès complet au disque, et ajoute le fichier `python` qui se trouve dans `.venv/bin/`. Ou passe à la phase 2.

Pour désactiver : `launchctl unload ~/Library/LaunchAgents/com.deezerstats.sync.plist`.

### Windows (Planificateur de tâches)

Dans PowerShell, **depuis le dossier du projet**, lance :

```powershell
$dir = (Get-Location).Path
schtasks /Create /SC MINUTE /MO 30 /TN "DeezerStats sync" /TR "cmd /c cd /d `"$dir`" && .venv\Scripts\python.exe -m scripts.sync"
```

Pour supprimer la tâche : `schtasks /Delete /TN "DeezerStats sync" /F`.

---

## 5. Passer en ligne : la synchro sur GitHub, même ordinateur éteint

La base de données est un fichier SQLite rangé **dans le dépôt GitHub lui-même**, sur une branche à part nommée `data`. Aucun compte de base de données n'est nécessaire.
- La branche `data` ne contient qu'**un seul commit, remplacé à chaque synchro** : le dépôt ne grossit pas, et la branche `main` ne contient que le code.
- ⚠️ **Le dépôt étant public, ta base (historique horodaté, favoris, playlists) est lisible par tout le monde**, comme le site lui-même. Pour la rendre privée, passe le dépôt en privé : la synchro marche pareil, mais le site Streamlit devra être configuré autrement (demande-moi).

### 5.1 Le dépôt

Le code est déjà sur https://github.com/theodorejl/Music-Data-Webapp, et la base y est publiée sur la branche `data`.

### 5.2 Configurer le secret et le profil

Sur la page du dépôt : **Settings > Secrets and variables > Actions**.

| Où | Nom | Valeur |
|---|---|---|
| onglet **Secrets** | `DEEZER_ARL` | ton cookie arl |
| onglet **Variables** | `DEEZER_PROFILE` | `TBTC` |
| onglet **Variables** (optionnel) | `MUSICBRAINZ_CONTACT` | ton e-mail ou l'adresse du dépôt |

### 5.3 Activer le robot de synchro

1. Onglet **Actions** du dépôt → **Deezer sync** → **Run workflow** pour un premier essai.
2. Au bout de 1 à 2 minutes, la pastille doit être verte ✅.

Ensuite, à chaque passage, toutes les 30 minutes, GitHub :
1. récupère la base publiée ;
2. ajoute tes nouvelles écoutes ;
3. complète les pochettes et les genres ;
4. republie la base.

À savoir :
- Les crons GitHub sont souvent retardés de quelques minutes. Ce n'est pas grave : Deezer garde les 100 dernières écoutes.
- En cas d'échec, par exemple si le cookie a expiré, **GitHub t'envoie un e-mail**.
- Sur un dépôt public, GitHub met en pause les synchros planifiées après **60 jours sans commit sur `main`**. Il t'envoie un e-mail avant. Pour relancer : onglet Actions → « Enable workflow ».

### 5.4 Et sur ton ordinateur ?

« Lancer l'app » et le bouton « Actualiser » font la même chose que GitHub, dans cet ordre :
1. **récupérer** la base publiée ;
2. synchroniser ;
3. **republier**.

La base de ton Mac et celle de GitHub restent donc identiques. La récupération ne remplace pas ta base : elle y fusionne la version publiée, et ce qui n'existe que chez toi (tes corrections admin, par exemple) est conservé.

Commandes manuelles : `python -m scripts.cloud_db pull` (récupérer) et `python -m scripts.cloud_db push` (publier).

La synchro automatique locale (`Activer la synchro automatique.command`) devient facultative.

## 6. Publier l'app sur Streamlit Community Cloud

1. Va sur <https://share.streamlit.io> et connecte-toi avec GitHub.
2. Clique sur **Create app**, puis **Deploy a public app from GitHub**.
   - Repository : `theodorejl/Music-Data-Webapp`
   - Branch : `main`
   - Main file path : **`app/Home.py`**
3. Ouvre **Advanced settings** :
   - Python version : **3.12**
   - Secrets : colle ceci.
     ```toml
     DATA_URL = "https://raw.githubusercontent.com/theodorejl/Music-Data-Webapp/data/deezer_stats.db.gz"
     TIMEZONE = "Europe/Zurich"
     ```
     🚫 **Ne mets jamais `DEEZER_ARL` ici.**
4. Clique sur **Deploy**.

Le site lit une copie de la base publiée et la rafraîchit toutes les 10 minutes. Il est en lecture seule : les corrections (page admin) se font depuis l'app sur ton ordinateur, et sont publiées à la prochaine actualisation.


## 7. En cas de problème

### Le cookie a expiré

**Symptômes** : tu reçois un e-mail d'échec de GitHub Actions, ou la synchro locale affiche `DEEZER COOKIE PROBLEM`. Dans l'app, le point en bas du rail de navigation (à gauche) passe au rose.

1. Reconnecte-toi sur deezer.com et récupère le nouveau `arl` (étape 2).
2. Remplace-le dans `.env` (local) **et** dans le secret GitHub `DEEZER_ARL` (Settings > Secrets and variables > Actions > `DEEZER_ARL` > Update).
3. Relance : `python -m scripts.sync`, ou « Run workflow » sur GitHub.

Si tu penses que ton cookie a fuité, déconnecte-toi de Deezer, change ton mot de passe Deezer, puis récupère un nouveau cookie.

### La synchro échoue pour une autre raison

- **En ligne** : onglet **Actions**, clique sur le passage en échec, puis sur l'étape « Sync Deezer history » pour lire le message. Si Deezer a renvoyé une réponse inattendue, elle est jointe au passage, dans **Artifacts > sync-logs**. Le cookie y est masqué.
- **En local** : le message s'affiche dans le terminal. Les réponses inattendues sont enregistrées dans le dossier `logs/`.
- `No storage configured` : le workflow a été modifié ; il doit garder `DEEZER_STATS_STORAGE: git`.

### Deezer a changé son API interne

L'app utilise une API **non officielle** : Deezer peut la modifier sans prévenir.

1. Lance le diagnostic :
   ```bash
   python -m scripts.diagnose_deezer
   ```
   Il teste les méthodes connues avec ton cookie, affiche ce qui marche et enregistre les réponses brutes dans `logs/diagnose_*.json`.
2. Si aucune méthode ne marche, regarde ce qu'utilise le site lui-même :
   - Sur deezer.com, ouvre ton profil, puis la page **Historique** (« Écoutés récemment »).
   - Ouvre les outils de développement (Cmd + Option + I ou F12), onglet **Network** (Réseau).
   - Dans le filtre, tape `gw-light`, puis recharge la page (Cmd + R ou F5).
   - Clique sur les requêtes : dans l'URL, le paramètre `method=` donne le nom de la méthode ; l'onglet **Payload** montre les paramètres envoyés.
3. Mets à jour la liste `attempts` dans `core/deezer_gw.py`, dans la fonction `get_history_raw`, ou demande de l'aide en montrant la sortie du diagnostic. Ne montre jamais ton cookie.

---

## Excel, albums & playlists, affiche A3

### Tes données en Excel, mises à jour automatiquement

Après chaque synchro locale, deux classeurs sont réécrits dans le dossier **`Exports Excel/`** du projet :

| Fichier | Onglets |
|---|---|
| `Historique des écoutes.xlsx` | Écoutes (toutes, sans limite), Titres, Albums, Artistes, Par jour |
| `Bibliothèque - albums et playlists.xlsx` | Albums favoris, Playlists, Titres des playlists |

- Si un fichier est ouvert dans Excel au moment de la synchro, il n'est pas mis à jour cette fois-là : un message le signale.
- Ces fichiers contiennent tes données personnelles : ils sont exclus de git.
- Dans l'app, des boutons « Télécharger en Excel » existent aussi : page Journal (écoutes filtrées), page Classements (tableaux) et page Bibliothèque.
- Pour désactiver ces copies, mets `EXCEL_DIR=off` dans `.env`.

### Page « Bibliothèque » (albums & playlists)

La synchro relève aussi, toutes les 6 heures au plus, les **albums favoris** et les **playlists** du profil : les siennes et celles ajoutées en favori, avec tous leurs titres. La page les croise avec ton historique :

- **Albums favoris** : répartition par décennie de sortie, artistes et genres les plus présents, ajouts par mois, et la liste complète, triable et cherchable.
- **Playlists** : playlists les plus écoutées, artistes les plus présents, part de chaque playlist réellement écoutée. Clique sur une playlist pour voir ses titres.
- **Exports** :
  - tout télécharger en Excel ;
  - générer l'**affiche A3 paysage** (PDF) de tous tes albums favoris : pochettes en grille, avec sous chacune le nom de l'album, sa date de sortie et l'artiste. La taille des pochettes s'adapte pour que tout tienne sur la page. Avec 336 albums, ça donne une grille de 24 × 14 et des pochettes d'environ 14 mm.

Pour forcer un rechargement immédiat de la bibliothèque : `python -m scripts.sync --library`.

---

## Recommandations (page « Pour toi »)

La page **Pour toi** propose des titres que tu n'as **jamais** écoutés, trouvés par trois moteurs qui partent de ton historique (la période choisie en haut de la page) et de l'API publique de Deezer. Le cookie `arl` n'est jamais utilisé ici, donc la page marche aussi sur le site en ligne.

1. **Les voisins** (graphe d'artistes) : pour chacun de tes 10 artistes favoris, Deezer connaît les artistes qui lui ressemblent. Un voisin gagne des points selon le temps que tu passes sur l'artiste de départ et selon sa proximité ; on garde un titre phare par nouvel artiste.
2. **Tes genres** (profil de goût) : ce qui est en tête des classements Deezer dans chacun de tes genres, réparti selon la part de chaque genre dans ton écoute. Un titre par artiste, uniquement des artistes nouveaux pour toi.
3. **Ton moment** (contexte) : la radio Deezer des artistes que tu écoutes le plus à ce moment de la journée (nuit, matin, après-midi, soir), en privilégiant les artistes inconnus.

Les trois moteurs ne se répètent pas : un même titre n'apparaît qu'une fois. Clique sur une pochette pour écouter **30 s**. Le lien de l'extrait est demandé à Deezer au moment du clic, car ces liens expirent au bout d'environ 15 minutes.

La **carte** place chaque recommandation dans le territoire de son genre, reliée à l'artiste dont elle vient. On peut zoomer (molette ou pincement), se déplacer (glisser) et écouter (clic). Les résultats sont gardés 6 heures, et le bouton **Nouvelles idées** les recalcule.

## Récupérer l'historique plus ancien (export Deezer)

L'historique de Deezer ne renvoie **que les 100 dernières écoutes** : c'est une limite de Deezer, pas de l'app. L'app, elle, garde **tout** ce qu'elle a relevé, sans limite.

Pour récupérer les écoutes **antérieures**, Deezer fournit sur demande une copie de tes données personnelles, avec ton historique d'écoute complet et la durée réellement écoutée :

1. Sur deezer.com, **connecté au profil voulu** (TBTC), ouvre Mon compte > Paramètres > Confidentialité > **Mes données personnelles**, et demande l'export. Deezer envoie un lien par e-mail, en général sous quelques jours.
2. Télécharge le fichier `.xlsx`, puis prévisualise l'import sans rien écrire :
   ```bash
   python -m scripts.import_deezer_export "chemin/vers/le/fichier.xlsx" --dry-run
   ```
3. Si le résumé est correct, lance l'import :
   ```bash
   python -m scripts.import_deezer_export "chemin/vers/le/fichier.xlsx"
   ```

Les écoutes déjà relevées par la synchro ne sont pas importées une deuxième fois : même titre à 3 minutes près. Tu peux relancer l'import sans risque.

Les dates du fichier sont supposées en UTC. Si les heures importées sont décalées, relance avec `--tz Europe/Zurich`.

> Le format exact de ce fichier n'est pas documenté publiquement. L'import reconnaît les colonnes par leur nom, en anglais ou en français. S'il ne trouve pas la feuille d'historique, il affiche la liste des feuilles et colonnes trouvées : envoie-la-moi pour l'adapter.

---

## Fonctionnement et choix techniques

### Ce que Deezer fournit (mesuré le 28/10/2026)

- La méthode `user.getSongsHistory` renvoie les **100 dernières écoutes**, de la plus récente à la plus ancienne. Il n'y a pas de pagination au-delà.
  - Ces 100 écoutes couvraient environ **29 heures** sur le profil TBTC, et environ un mois sur le profil principal, moins utilisé.
- **L'historique est propre à chaque profil** d'un compte Family. La synchro change de profil avec `user.loginMulti` (réglage `DEEZER_PROFILE`).
  - Une écoute répétée du même titre apparaît bien plusieurs fois.
- Chaque écoute a un horodatage (`TS`, le début de l'écoute) et la durée du **morceau**.
- **Deezer ne donne pas le temps réellement écouté.**
- **Fréquence choisie : toutes les 30 minutes.** Pour perdre des écoutes, il faudrait en enchaîner plus de 100 en 30 minutes, soit un titre toutes les 18 secondes. En revanche, **sur TBTC, une journée sans synchro suffit à perdre des écoutes** : d'où l'importance de la phase 2.
- Si une synchro voit que les 100 écoutes reçues ne rejoignent pas les dernières déjà enregistrées, elle note un **« trou possible entre X et Y »**. Tu le vois discrètement en bas du rail de navigation de l'app (« n trou(s) »).

### Durée d'écoute estimée

Comme Deezer ne fournit pas le temps écouté, l'app l'estime :

> **durée écoutée ≈ min(durée du titre, début de l'écoute suivante − début de cette écoute)**

La dernière écoute d'une session reçoit la durée complète du titre. Ces durées sont marquées comme estimées : astérisque `*` dans les tableaux et note sous les chiffres. Elles servent aussi à repérer les **titres zappés** (page Rythmes) : un titre compte comme zappé dès qu'il s'arrête avant sa fin, quel que soit le moment. Deezer n'inscrit dans son historique que les écoutes d'environ 30 s ou plus, donc les zappings plus rapides n'y apparaissent pas. Si une future source fournit la vraie durée, elle sera utilisée telle quelle.

### Genres

- Le genre d'une écoute est celui de **l'album sur Deezer**. À défaut, c'est le genre MusicBrainz de l'album, puis celui de l'artiste.
- Les tags MusicBrainz, avec leur nombre de votes, sont affichés sur les fiches artiste et album.
- La page **Corrections (admin)** permet de forcer le genre d'un album ou de renommer et regrouper des genres.

### Corrections (admin)

C'est la seule page qui écrit en base. Elle est protégée par `ADMIN_PASSWORD` et permet de :
- fusionner des artistes ou des albums en double ;
- forcer un genre ;
- masquer une écoute erronée.

Les corrections sont stockées à part, dans la table `aliases`, et appliquées au calcul des statistiques. **Les données brutes ne sont jamais modifiées**, et chaque correction peut être supprimée.

### Structure du projet

```
app/                 application Streamlit (lecture seule, sauf la page admin)
  Home.py            point d'entrée, minuscule et stable : streamlit run app/Home.py
  shell.py           rail de navigation, recherche, actualisation, fond vivant
  devreload.py       rechargement à chaud de tout le projet (aucune relance nécessaire)
  views/             une page par fichier (pas « pages/ » : ce nom active un ancien mode de Streamlit)
  components/        thème « Noto » (panneaux en dégradé), blocs, graphiques Plotly, visualisations,
                     interactive.py : roue des genres (D3), carte et cartes de recommandations, extraits
  assets/theme.css   tout le style : familles de couleurs, panneaux, rail, puces
  i18n/              fr.json, en.json + t("clé")
core/
  config.py          réglages : variables d'environnement > st.secrets > .env
  db.py, models.py   SQLAlchemy (SQLite ou Postgres) et tables
  deezer_gw.py       client de l'API interne (cookie arl), derrière HistorySource.fetch_recent()
  deezer_public.py   api.deezer.com (métadonnées, pochettes, extraits)
  musicbrainz.py     tags de genres (1 requête par seconde)
  sync.py            relevé → dédoublonnage → stockage → enrichissement
  stats.py           toutes les statistiques (fonctions pures sur des DataFrames)
  recommend.py       les trois moteurs de recommandation (API publique Deezer)
scripts/             sync, dev_server, cloud_db, diagnose_deezer, migrate_sqlite_to_postgres, seed_demo
tests/               pytest
.github/workflows/   synchro toutes les 30 min
```

---

## Limites connues

- **API non officielle.** L'app lit ton historique via l'API interne du lecteur web Deezer. Elle peut changer ou casser à tout moment (voir l'étape 7). Cet usage **n'est pas prévu par les conditions d'utilisation de Deezer** : utilise-la pour toi seul, avec modération (une requête toutes les 30 minutes).
- **Fenêtre d'historique limitée par Deezer** aux 100 dernières écoutes : des pertes sont possibles si la synchro ne tourne pas assez souvent (ordinateur éteint en phase 1). Pour le passé, voir l'import de l'export Deezer ci-dessus.
- **Durées d'écoute estimées**, voir plus haut. Les titres zappés de la page Rythmes reposent sur cette estimation. Une pause longue au milieu d'un titre, ou un titre passé juste avant de fermer l'app, peuvent fausser l'estimation.
- **Titres passés très vite** : il n'est pas encore confirmé que Deezer inscrive dans l'historique les titres passés au bout de quelques secondes.
  - Pour le vérifier : écoute un titre 5 secondes puis passe au suivant, lance `python -m scripts.sync`, puis regarde la page Historique.
  - Si le titre n'apparaît pas, c'est Deezer qui ne l'enregistre pas : aucun outil basé sur cet historique ne pourra le voir.
- Les **extraits de 30 s** viennent de l'API publique Deezer. Certains titres n'en ont pas.
- **Profil public** : sur Streamlit Cloud, tout le monde peut voir tes statistiques et ton historique horodaté. C'est voulu.
