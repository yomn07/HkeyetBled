# Hkeyet Bled RAG — Lot 1 : Corpus et collecte

Pipeline qui construit le corpus de l'assistant **Hkeyet Bled** (patrimoine, artisanat, gastronomie, coutumes tunisiennes) :
**collecte → nettoyage → déduplication → annotation (région, thème) → JSONL + fiche de corpus.**

Livrables du lot : `data/corpus.jsonl` (dataset nettoyé) et `docs/fiche_corpus.md` (fiche de corpus avec couverture par thème et par région).

---

## 1. Installation (5 min)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10 ou plus récent.

**Avant la collecte**, ouvrez `config/sources.yaml` et mettez l'adresse e-mail de l'équipe dans `http.user_agent`. Wikimedia exige un User-Agent avec un contact.

## 2. Lancer

```bash
# 1) Test rapide (≈ 2 min) : 5 éléments par source, pour vérifier que tout marche
python run_pipeline.py all --limit 5

# 2) Si c'est bon : on repart de zéro pour la vraie collecte (≈ 20-30 min, 1 requête/s)
rm -rf data/raw
python run_pipeline.py all
```

La collecte **reprend où elle s'est arrêtée** : si le script est interrompu, relancez la même commande et les pages déjà téléchargées ne seront pas re-téléchargées (cache `data/raw/`).

Autres commandes utiles :

| Commande | Effet |
|---|---|
| `python run_pipeline.py collect --only wikipedia wikivoyage` | ne collecter que certaines sources |
| `python run_pipeline.py collect --langs fr,ar` | sans l'anglais |
| `python run_pipeline.py process report` | refaire nettoyage + annotation + fiche, sans re-télécharger |
| `python run_pipeline.py process report --keep-diacritics` | garder les harakat arabes |
| `python -m pytest -q tests/` | tests hors-ligne (aucun accès réseau nécessaire) |

## 3. Ce que vous obtenez

```
data/
  raw/                       # pages brutes (HTML/texte) + métadonnées, cache de collecte
    wikipedia_missing.txt    # titres introuvables -> à corriger dans sources.yaml
    web_failures.tsv         # pages web en échec (robots.txt, 404, texte trop court)
  corpus.jsonl               # ★ LIVRABLE : dataset nettoyé et annoté (pour l'index local)
  corpus_public.jsonl        # version partageable (texte retiré pour les sources non libres)
  rejected.jsonl             # documents écartés + raison (doublon, trop court, hors sujet)
docs/
  fiche_corpus.md            # ★ LIVRABLE : fiche de corpus (sources, licences, couverture, schéma)
  couverture.png             # graphique thème × macro-région (pour le rapport / les slides)
  couverture_gouvernorats.csv
  couverture_theme_x_region.csv
  echantillon_validation.csv # 50 documents à vérifier à la main
```

### Format d'un document (contrat avec le Lot 2)

Une ligne JSON par document :

```json
{"id": "wikipedia_fr_amphitheatre-d-el-jem_b24529", "title": "Amphithéâtre d'El Jem", "lang": "fr",
 "text": "L'amphithéâtre d'El Jem est un amphithéâtre romain…\n## Histoire\n…",
 "url": "https://fr.wikipedia.org/wiki/Amphith%C3%A9%C3%A2tre_d%27El_Jem",
 "source": "wikipedia", "source_type": "encyclopedie", "license": "CC BY-SA 4.0", "redistributable": true,
 "region": "Mahdia", "region_ar": "المهدية", "region_macro": "Centre-Est", "regions": ["Mahdia", "Sousse", "Sfax"],
 "theme": "patrimoine_archeologique", "themes": ["patrimoine_archeologique"],
 "group_id": "g_3f2a…", "categories": […], "n_words": 1830, "n_chars": 11204, "revid": 2193…,
 "retrieved_at": "2026-11-11T09:12:44+00:00", "annotation": "auto"}
```

À transmettre au **Lot 2 (indexation)** :
- les lignes `## Titre` marquent les sections : bon point de coupe pour le chunking ;
- chaque chunk doit garder `url`, `title`, `region`, `theme`, `lang` en métadonnées (citations du Lot 4, filtres du Lot 3) ;
- `group_id` relie les versions FR/AR/EN d'un même article.

Lecture en Python :

```python
import pandas as pd
df = pd.read_json("data/corpus.jsonl", lines=True)
df.groupby(["theme", "lang"]).size()
```

Thèmes : `patrimoine_archeologique`, `architecture_medinas`, `artisanat`, `gastronomie`, `coutumes_fetes`, `musique_arts`, `nature_paysages`, `histoire`, `langue_savoir_vivre`.
Régions : les 24 gouvernorats (`config/regions.yaml`) ou `National`, plus 7 macro-régions.

## 4. Sources et licences

| Source | Accès | Licence | Dans `corpus_public` |
|---|---|---|---|
| Wikipédia FR (pivot) + AR/EN (liens interlangues) | API MediaWiki | CC BY-SA 4.0 | texte complet |
| Wikivoyage FR/EN (itinéraires) | API MediaWiki | CC BY-SA 4.0 | texte complet |
| UNESCO – fiches patrimoine mondial | scraping, robots.txt respecté | © UNESCO | lien seulement |
| INP – sites et monuments | scraping (crawl limité) | © INP | lien seulement |
| ONTT – brochures Discover Tunisia (PDF) | téléchargement | © ONTT | lien seulement |
| Blogs culturels | scraping | © auteurs | lien seulement |

**Ajouter des sources** : dans `config/sources.yaml`, ajoutez un titre Wikipédia à la liste du bon thème (`seeds`), ou une URL dans `web > blogs > urls`. Relancez ensuite `collect` puis `process report`. Les sites tunisiens changent souvent d'adresse : si une URL apparaît dans `web_failures.tsv`, ouvrez-la dans un navigateur et corrigez-la.

### Fiches rédigées par l'équipe (expressions, proverbes, savoir-vivre)

Le dialecte et les comportements du quotidien sont peu documentés en ligne. Le dossier `config/manual/` contient donc des fiches Markdown rédigées par l'équipe :
- `expressions_tunisiennes.md` : salutations, mots courants, proverbes en derja ;
- `savoir_vivre_tunisie.md` : hospitalité, souk, tenue, Ramadan, café, hammam.

Ce sont des **brouillons** (`verified: false`) : relisez-les, corrigez-les, ajoutez les expressions et habitudes de vos régions, puis mettez `verified: true`. Seules les fiches vérifiées entrent dans le corpus (source `equipe`, licence CC BY 4.0). Pour ajouter une fiche, copiez l'un de ces fichiers et gardez le même en-tête.

## 5. Méthode (à présenter à la soutenance)

1. **Collecte responsable** : API officielle pour Wikimedia, User-Agent identifié, 1 requête/s par site, `robots.txt` vérifié, révision Wikipédia (`revid`) enregistrée pour la reproductibilité.
2. **Nettoyage HTML** : on retire les infobox, tableaux, bandeaux, navbox, appels de notes `[1]`, et tout ce qui suit « Références / Liens externes / مراجع ». Pour les pages web, on extrait le contenu principal (trafilatura) et on supprime les menus et pieds de page répétés.
3. **Encodage arabe** : réparation du mojibake (`Ã©` → `é`, ftfy), normalisation NFKC (formes de présentation `ﻣﺪﻳﻨﺔ` → `مدينة`), suppression du tatweel `ـ`, des harakat et des caractères invisibles (marques bidi, ZWJ). `common.normalize_arabic_for_search()` (alef, ى/ي, ة/ه) est fournie au Lot 3 pour BM25.
4. **Déduplication** : doublons exacts (hash), quasi-doublons par MinHash/LSH (Jaccard ≥ 0,8), copies partielles (≥ 80 % du texte déjà présent ailleurs, par ex. un blog qui recopie Wikipédia) et paragraphes répétés. On garde la source la plus fiable. Les traductions ne sont pas des doublons.
5. **Annotation** : la région vient d'un gazetteer de 24 gouvernorats (près de 400 villes et sites en FR et en AR, avec gestion des préfixes arabes و/ب/ال). Le thème vient d'un lexique trilingue (score = titre + catégories + densité de mots-clés). Les documents sans aucun lien avec la Tunisie sont écartés.
6. **Contrôle qualité** : remplissez `docs/echantillon_validation.csv` (oui/non), calculez la précision et reportez-la dans la section 9 de la fiche. Corrigez les erreurs dans `config/overrides.csv`, puis relancez `python run_pipeline.py process report`.

## 6. Checklist du Lot 1

- [ ] Contact mis dans `user_agent`
- [ ] `python run_pipeline.py all --limit 5` fonctionne
- [ ] Collecte complète lancée, `wikipedia_missing.txt` et `web_failures.tsv` relus
- [ ] Thèmes ou gouvernorats « ⚠ » de la fiche renforcés (ajout de titres ou d'URL), puis nouvelle collecte
- [ ] Échantillon de 50 documents vérifié, précisions reportées dans la fiche
- [ ] `corpus.jsonl` et la section « Schéma » envoyés au Membre 2 (Lot 2)
