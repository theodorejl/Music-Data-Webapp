# Un modèle de genre fiable pour chaque artiste

Spécification validée par sections le 29/10/2026. Elle remplace la façon dont `core/atlas.py` décide du genre d'un artiste et de sa place sur la carte.

## 1. Le problème

Mesures faites sur ta base le 29/10/2026 :

- 8 438 artistes sont placés sur la carte. Seuls 2 240 (27 %) sont posés sur un genre précis.
- 5 235 (62 %) n'ont aucune source de genre. Ils sont devinés d'après le genre principal des artistes qui partagent leurs playlists, puis posés en nuage au milieu de ce grand genre, « au milieu de nulle part ».
- Les sources (Wikidata, MusicBrainz, Discogs, Last.fm, Deezer) votent avec des poids fixés à la main. Rien ne vérifie qu'un genre est cohérent avec les artistes proches.
- Des artistes sont parfois vus hors de la carte. Ce cas n'a pas été reproduit : dans les données, aucun point n'est hors de son territoire, y compris au zoom photo sur les zones les plus denses.

## 2. Ce qui a été décidé

| Question | Décision |
|---|---|
| Le genre dominant d'un artiste multi-genre | Celui de **sa carrière** : celui sur lequel les sources et ses artistes liés s'accordent le plus. La carte Univers en mode albums montre déjà chaque album à sa place. |
| L'analyse du son (Discogs-EffNet sur les extraits Deezer) | **Plus tard**, si les résultats ne suffisent pas. Hors du périmètre de cette spécification. |
| Un artiste aux indices faibles | Toujours posé **sur le genre précis le plus probable**, jamais en nuage. |
| La certitude | Calculée et utilisée par le modèle et l'évaluation, **jamais affichée**. L'infobulle reste comme aujourd'hui. |
| L'approche | **Preuves + fiabilité mesurée + voisins** (sections 4 à 6). |

## 3. Les données

### 3.1 L'index Every Noise (nouvelle source)

La carte est construite sur les 6 291 genres d'Every Noise at Once (Glenn McDonald), qui sont les genres que Spotify attribuait à chaque artiste. Spotify ne fournit plus ces genres par son API (champ abandonné, vide pour les nouvelles apps depuis février 2026). En revanche, chaque page genre d'Every Noise (`https://everynoise.com/engenremap-<genre>.html`) liste environ 150 artistes avec leur identifiant Spotify et leur nom.

- `scripts/build_everynoise_index.py` récupère une fois les 6 291 pages, à raison d'une par seconde (environ 1 h 45).
  - Il reprend où il s'est arrêté.
  - Il garde les pages brutes dans `data/everynoise/`, hors du dépôt.
- Il écrit `app/assets/everynoise_artists.json.gz`, rangé dans le dépôt : Every Noise ne bouge plus depuis fin 2023, donc l'index est figé.
  - Pour chaque artiste : identifiant Spotify, nom, et liste des genres où il figure, avec son rang dans chaque genre.
  - La taille est estimée à environ 10 Mo, à vérifier. Au-delà de 25 Mo, on ne garde que les artistes présents dans ta discothèque ou liés à elle.
- `core/everynoise.py` lit une page, construit l'index, le charge et retrouve les genres d'un artiste.
- La source est citée dans l'app et le README, comme Every Noise le demande.
- Essai du 29/10/2026 : avec 60 pages sur 6 291, on retrouve déjà 1 611 de tes artistes par leur nom, dont 450 sans aucune source aujourd'hui.

### 3.2 L'identité (pas d'homonymes)

1. **Par identifiant Spotify**, d'abord :
   - Wikidata (propriété P1902), ajoutée à la requête que l'app fait déjà par identifiant Deezer (environ 32 000 artistes de Wikidata ont les deux identifiants) ;
   - les liens « url-rels » de MusicBrainz, que l'app demande déjà.
   - L'identifiant est rangé dans `tags` avec `entity_type = "artist_spotify"`, comme les labels (`"artist_label"`). Il n'y a donc pas de nouvelle colonne, et pas de migration.
2. **Par nom**, sinon, une fois le nom normalisé (minuscules, sans accents ni ponctuation) :
   - accepté s'il est unique dans l'index ;
   - s'il y a plusieurs homonymes, on garde celui dont les genres s'accordent le mieux avec les autres preuves de l'artiste et avec ses voisins, à condition qu'il se détache nettement ; sinon, aucun.
   - La preuve « Every Noise par le nom » est une source à part, dont la fiabilité est mesurée comme les autres (section 4.2).

### 3.3 Les artistes liés Deezer (nouvelle source)

- L'API publique `api.deezer.com/artist/{id}/related` donne jusqu'à 20 artistes liés, par ordre de proximité. Elle est appelée par `DeezerPublicClient`, qui respecte le quota de 45 requêtes par 5 secondes. Pour tes 8 438 artistes, cela prend environ 15 minutes.
- Les liens sont rangés dans une nouvelle table `artist_related` : `artist_id`, `related_id`, `rank`, `related_name`.
- Les artistes liés qui ne sont pas dans ta discothèque comptent aussi : leurs genres viennent de l'index Every Noise, par leur nom.
- Exemple du 29/10/2026 : pour Lewis OfMan, Deezer renvoie L'Impératrice, Myd, Parcels, Polo & Pan, Yuksek, Bon Voyage Organisation…

### 3.4 Les sources conservées

Wikidata, MusicBrainz (genres et tags), Discogs (styles et genres), Last.fm (avec la clé `LASTFM_API_KEY`), les genres Deezer des albums, et les playlists. Leurs mots sont lus sur l'arbre des genres par `atlas.meaning()`, comme aujourd'hui.

### 3.5 Le résultat rangé dans la base

Une nouvelle table `artist_genre` est recalculée entièrement à chaque classement. Elle contient :
- `artist_id`, `main`, `sub`, `genre` ;
- `confidence` (interne) ;
- `words` et `sources`, pour l'infobulle ;
- `updated`.

`core/cloud_db.py` la traite comme une table « instantané », remplacée en bloc. `artist_related` est fusionnée comme les autres tables. Les deux tables sont ajoutées à la liste `TABLES` utilisée par la fusion.

## 4. Le modèle (`core/genremodel.py`)

### 4.1 Les preuves

Pour chaque artiste et chaque source, les preuves forment une distribution de masse sur l'arbre des genres de la carte (`core/genretree.py`) : 22 genres principaux, 162 sous-genres et 6 291 genres précis.

- **Every Noise** : une masse sur chaque genre précis où l'artiste figure. Elle est plus forte pour un rang élevé : `1 / (1 + rang / 50)`.
- **Les autres sources** : chaque mot est lu par `meaning()`.
  - Un genre précis reçoit sa masse sur ce genre.
  - Un sous-genre la reçoit sur ce sous-genre.
  - Un genre principal la reçoit sur ce genre principal.
  - La force du mot est celle d'aujourd'hui (`_strength`) : votes MusicBrainz, fréquence Last.fm, etc.
- La masse d'un genre précis compte aussi pour son sous-genre et son genre principal, et celle d'un sous-genre pour son genre principal.

### 4.2 La fiabilité des sources (mesurée)

Le principe est celui de Dawid-Skene, en version simple : une fiabilité par couple (source, genre principal). Le calcul :
1. On part des poids actuels (`WEIGHT`) et d'un consensus calculé avec eux.
2. Pour chaque source *s* et chaque genre principal *m*, on prend les artistes où *m* est le genre principal le plus fort selon *s*. La fiabilité est la part de ces artistes où le consensus **des autres sources** donne aussi *m* en premier. On lisse avec un a priori de 10 artistes au poids actuel.
3. Le consensus est recalculé avec ces fiabilités, et on recommence jusqu'à ce que rien ne bouge (au plus 20 tours).
4. Les fiabilités sont bornées entre 0,2 et 3 fois le poids de départ. Aucune source ne peut disparaître ni tout dominer.

Les fiabilités obtenues sont écrites dans le journal du classement, pour qu'on puisse les relire.

### 4.3 Les voisins : propagation et contrôle

Le graphe des voisins :
- **Artistes liés Deezer** : poids `1 / (1 + rang / 5)`.
- **Playlists partagées** : poids `0,3 × min(1, playlists communes / 3)`. Les playlists de plus de 300 titres sont ignorées, car trop mélangées.

La propagation (au plus 10 tours, arrêt quand plus rien ne bouge) :
- Distribution d'un artiste : `P = normaliser(preuves propres + λ × Σ poids × P du voisin)`.
- λ diminue quand les preuves propres sont nombreuses : `λ = 1 / (1 + masse propre)`. Sans preuve propre, les voisins décident seuls.
- Les voisins hors de ta discothèque ont une distribution fixe, celle d'Every Noise. S'ils n'y figurent pas, ils sont ignorés.

Le contrôle de cohérence :
- **Preuves propres faibles** (masse propre < 1, par exemple seulement « Pop » de Deezer) et voisins à plus de 60 % sur un autre genre principal : les voisins l'emportent.
- **Preuves propres solides** : elles l'emportent. Le désaccord est gardé dans `confidence`, mais rien n'est affiché.

### 4.4 La décision

On descend l'arbre en choisissant à chaque fois le dominant, sur la carrière entière :
1. le genre principal dominant ;
2. le sous-genre dominant **dans ce genre principal** ;
3. le genre précis dominant **dans ce sous-genre**.

Un artiste multi-genre va donc dans son genre dominant : on ne fait jamais la moyenne de deux positions.

Si aucun genre précis n'est indiqué, on prend le genre précis le plus fréquent chez ses voisins dans ce sous-genre. À défaut, le genre le plus populaire du sous-genre, c'est-à-dire celui de plus petit rang dans Every Noise.

### 4.5 La certitude (interne)

| Niveau | Condition |
|---|---|
| `sure` | Au moins deux sources fiables d'accord sur le sous-genre, ou une correspondance Every Noise exacte par identifiant Spotify. |
| `likely` | Une seule source, ou une majorité avec désaccord. |
| `neighbours` | Aucune preuve propre : décidé par les voisins. |

La certitude sert à l'évaluation et au réglage. Elle n'est pas affichée.

## 5. La place sur la carte (`core/atlas.py`)

- `place()` lit `artist_genre` au lieu de décider lui-même. `decide()` et `meaning()` restent pour lire les mots.
- Chaque artiste est posé sur le point de son genre précis (`genretree.position()`).
- Les artistes d'un même genre s'enroulent en **spirale de tournesol** autour de ce point, les plus écoutés au centre :
  - rayon `c × √i` ;
  - angle `i × 137,5°` ;
  - `c` est réglé pour que les photos ne se recouvrent pas au zoom 7.
- Chaque point est retenu dans son territoire, comme aujourd'hui.
- `place_albums()` place un album d'après ses propres genres, puis d'après la décision de son artiste dans `artist_genre`.
- L'infobulle ne change pas : genre, label, mots et sources.

## 6. Rien hors de la carte (rendu)

- Dans `SOUND_MAP_JS`, chaque élément dessiné est retenu dans son territoire après l'écartement anti-chevauchement : artistes, photos et découvertes. Si un point écarté sort, il est ramené le long de la droite vers le centre du territoire.
- Un test dans le navigateur, avec Playwright, vérifie à plusieurs zooms (1, 3, 8, 16) qu'aucun élément dessiné n'est hors de son territoire ni hors du contour.
- Une capture du cas vu par l'utilisateur sera demandée, pour confirmer que la cause est couverte.

## 7. Évaluation (`scripts/genre_eval.py`)

- **Artistes de référence** : ceux pour lesquels au moins deux sources indépendantes, ou Every Noise par identifiant, s'accordent sur le sous-genre.
- **Test à froid** : toutes les preuves propres des artistes de référence sont masquées, et le modèle ne voit que les voisins. On mesure le taux de bons genres principaux et de bons sous-genres, comparé à la méthode actuelle (les playlists).
- **Test à une seule source** : on ne garde qu'une source par artiste de référence, et on mesure le même taux.
- **Ancien contre nouveau** sur les mêmes artistes, avec la répartition des niveaux (genre précis, sous-genre, genre principal).
- **Lecture humaine** : 40 artistes tirés au hasard, avec leur genre décidé, à juger par l'utilisateur.
- Les chiffres sont donnés dans le compte rendu et repris dans le README.

## 8. Tests automatiques (écrits avant le code)

- Lecture d'une page Every Noise (extrait enregistré dans `tests/fixtures/`) : identifiants, noms, rangs.
- Identité : l'identifiant Spotify passe avant le nom, un homonyme ambigu est refusé.
- Fiabilité : sur un exemple jouet, une source toujours fausse voit sa fiabilité baisser.
- Propagation : un artiste sans preuve prend le genre de ses voisins.
- Contrôle : un « Pop » isolé contre des voisins tous en house donne de la house.
- Décision : un artiste à 60 % house et 40 % jazz va dans la house, sur un genre précis, jamais entre les deux.
- Spirale : tous les points restent dans leur territoire et ne se recouvrent pas.
- Fusion `cloud_db` : `artist_genre` est remplacée, `artist_related` est fusionnée.
- Garde-fous réels, à vérifier sur la vraie base après construction : Wally Badarou en jazz (fusion / jazz-funk), Lewis OfMan dans l'électronique ou l'indie française (nu disco, french indie pop…).
- Navigateur : rien hors de la carte (section 6).

## 9. Faire tourner

La première fois, sur ton ordinateur :
1. `python -m scripts.build_everynoise_index` : environ 1 h 45, reprend où il s'est arrêté.
2. `python -m scripts.enrich_artists --related --spotify-ids` : artistes liés Deezer (environ 15 min), identifiants Spotify (Wikidata en lot, quelques minutes ; MusicBrainz à 1 requête par seconde pour environ 2 000 artistes, environ 35 min).
3. `python -m scripts.classify_genres` : quelques secondes. Écrit `artist_genre` et affiche l'évaluation.

Ensuite, à chaque synchro (GitHub ou ton ordinateur) :
- les nouveaux artistes reçoivent leurs artistes liés et leur identifiant Spotify, dans le budget d'enrichissement ;
- puis le classement complet est recalculé, ce qui prend quelques secondes.

L'app lit `artist_genre` : la carte reste aussi rapide qu'aujourd'hui.

## 10. Hors périmètre

- L'analyse du son (Discogs-EffNet sur les extraits de 30 s) : prévue plus tard.
- Afficher la certitude.
- Changer l'arbre des genres ou le dessin de l'atlas.

## 11. Risques

- **Every Noise peut fermer ou bloquer.** L'index est rangé dans le dépôt après la première récupération, donc l'app n'en dépend plus.
- **Homonymes.** Ils sont limités par l'identifiant Spotify, et un nom ambigu n'est jamais accepté seul. Leur fiabilité est mesurée à part.
- **Index trop lourd.** On ne garde alors que les artistes de ta discothèque et leurs artistes liés.
- **Désaccord entre sources.** C'est attendu ([MediaEval AcousticBrainz](https://labs.acousticbrainz.org/mediaeval-genre-datasets/)) : la fiabilité mesurée par grand genre est faite pour ça.

## Sources

- [Every Noise at Once, archives et outils](https://github.com/ThatSINEWAVE/MusicGenreDB)
- [Spotify Web API, Get Artist : `genres` abandonné](https://developer.spotify.com/documentation/web-api/reference/get-an-artist), [signalement de février 2026](https://github.com/marcelmarais/spotify-mcp-server/issues/73)
- [Kim et al., propagation de tags, ISMIR 2009](https://www.cs.swarthmore.edu/~turnbull/Papers/Kim_TagPropagate_ISMIR09.pdf)
- [GATSY, graphe d'artistes et genres MusicBrainz](https://arxiv.org/pdf/2311.00635)
- [Réseaux d'artistes issus des playlists, propagation de labels](https://www.scitepress.org/Papers/2021/106786/106786.pdf)
- [Synthèse sur la découverte de vérité (Dawid-Skene et suites)](https://arxiv.org/abs/1505.02463)
- [Modèles Essentia, dont Discogs-EffNet](https://essentia.upf.edu/models.html)
