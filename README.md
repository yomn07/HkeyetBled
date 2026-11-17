# 🇹🇳 Hkeyet Bled — Assistant RAG du patrimoine tunisien

> *Hkeyet Bled* (حكايات بلاد, « histoires du pays ») est un assistant conversationnel qui fait découvrir le patrimoine,
> l'artisanat, la gastronomie et les traditions de Tunisie, en **français, anglais et arabe**.
> Il répond uniquement à partir d'un corpus vérifié, **cite ses sources** et **refuse** de répondre quand il ne sait pas.

- **Rapport d'évaluation** : [`evaluation/resultats/rapport_evaluation.md`](evaluation/resultats/rapport_evaluation.md)

---

## Sommaire

1. [Le projet](#1-le-projet)
2. [Architecture](#2-architecture)
3. [Les cinq lots](#3-les-cinq-lots)
4. [Résultats](#4-résultats)
5. [Installation](#5-installation)
6. [Utilisation](#6-utilisation)
7. [Tests et évaluation](#7-tests-et-évaluation)
8. [Structure du dépôt](#8-structure-du-dépôt)
9. [Limites et pistes d'amélioration](#9-limites-et-pistes-damélioration)
10. [Sources, licences et équipe](#10-sources-licences-et-équipe)

---

## 1. Le projet

### Problème
Les grands modèles de langage connaissent mal le patrimoine tunisien local : ils confondent les lieux, inventent des
monuments ou des dates, et ne disent pas d'où vient l'information. Le dialecte et les coutumes du quotidien sont
par ailleurs peu documentés en ligne.

### Solution : le RAG (*Retrieval-Augmented Generation*)
Au lieu de laisser le LLM répondre de mémoire, on **cherche d'abord** les passages pertinents dans un corpus de
documents fiables, puis on demande au LLM de répondre **uniquement à partir de ces passages**, en les citant.

### Fonctionnalités
- **Trilingue** : questions et réponses en français, anglais et arabe ; recherche interlangue (question en arabe, source en français).
- **Trois modes** : *Répondre* (réponse factuelle), *Raconter* (récit), *Itinéraire* (parcours de visite).
- **Carte interactive** des 24 gouvernorats : un clic filtre la recherche sur une région ; l'itinéraire est tracé sur la carte.
- **Filtre par thème** : 9 thèmes (archéologie, médinas, artisanat, gastronomie, coutumes et fêtes, musique et arts, nature, histoire, savoir-vivre).
- **Sources citées** `[1] [2]` avec titre, lien et licence de chaque document.
- **Refus** des questions hors sujet ou sans réponse dans le corpus.

---

## 2. Architecture

```
        ┌──────────────────────── HORS LIGNE (préparation) ────────────────────────┐
        │                                                                          │
        │   Lot 1 : CORPUS                       Lot 2 : INDEXATION                │
        │   Wikipédia, Wikivoyage, UNESCO,       découpage en chunks (400 tokens)  │
        │   INP, ONTT, blogs, fiches équipe  ──▶ embeddings multilingues (e5)  ──▶ index FAISS
        │   nettoyage, dédoublonnage,            8 474 chunks + métadonnées        │
        │   annotation région / thème                                              │
        │   1 163 documents                                                        │
        └──────────────────────────────────────────────────────────────────────────┘

        ┌──────────────────────── EN LIGNE (à chaque question) ────────────────────┐
        │                                                                          │
 Question ──▶ Lot 3 : RETRIEVAL ──────────▶ Lot 4 : GÉNÉRATION ──────▶ Lot 5 : INTERFACE
        │     filtres région/thème          garde-fous (périmètre, seuil)   Streamlit + carte
        │     BM25  +  recherche dense      prompt avec passages [1]…[n]    réponse citée
        │     fusion RRF, dédoublonnage     LLM (Qwen 2.5 / API)            sources + licences
        │     → 5 meilleurs passages        contrôle des citations          │
        └──────────────────────────────────────────────────────────────────────────┘
```

### Technologies

| Étape | Outils |
|---|---|
| Collecte | `requests`, API MediaWiki, `BeautifulSoup`, `lxml`, `trafilatura`, `pypdf` |
| Nettoyage | `ftfy`, normalisation Unicode, MinHash/LSH (déduplication) |
| Données | `pandas`, JSONL, `pyyaml` |
| Embeddings | `sentence-transformers` : `intfloat/multilingual-e5-base` (retenu), `BAAI/bge-m3`, MiniLM |
| Index vectoriel | `faiss-cpu` (`IndexFlatIP`, similarité cosinus) |
| Recherche lexicale | `rank_bm25` (BM25Okapi) |
| Reranker (option) | `BAAI/bge-reranker-v2-m3` |
| LLM | Ollama + `qwen2.5:7b-instruct` (défaut), ou toute API compatible OpenAI, ou Anthropic |
| Interface | `streamlit`, `plotly` (carte choroplèthe) |
| Évaluation | métriques maison (hit@k, MRR, citations, refus), `ragas` (option) |

---

## 3. Les cinq lots

### Lot 1 — Corpus · [`data preprocessing/`](data%20preprocessing/README.md)
- **Collecte responsable** : API officielle Wikimedia, User-Agent identifié, 1 requête/s, `robots.txt` respecté, révision Wikipédia enregistrée.
- **Nettoyage** : suppression des infobox, tableaux, notes et références ; extraction du contenu principal des pages web.
- **Arabe** : réparation du mojibake, normalisation NFKC, suppression du tatweel, des harakat et des caractères invisibles.
- **Déduplication** : doublons exacts (hash), quasi-doublons (MinHash/LSH, Jaccard ≥ 0,8), copies partielles ; les traductions sont reliées (`group_id`), pas supprimées.
- **Annotation** : région par gazetteer des 24 gouvernorats (~400 lieux FR/AR) ; thème par lexique trilingue.
- **Résultat** : `corpus.jsonl`, **1 163 documents**, et une fiche de corpus.

### Lot 2 — Indexation · [`indexation/`](indexation/README.md)
- **Chunking** par sections, fenêtres de 400 tokens avec 80 tokens de chevauchement ; titre et section ajoutés en tête de chaque chunk.
- **Comparaison de 3 modèles d'embeddings** sur 28 questions FR/AR/EN : e5 et bge-m3 à égalité (hit@5 = 0,89), MiniLM écarté (échoue en arabe).
- **Index FAISS** des trois modèles fournis dans le dépôt : **8 474 chunks**.

### Lot 3 — Retrieval · [`retrieval/`](retrieval/README.md)
- **Recherche hybride** : dense (sens, multilingue) + BM25 (noms propres), combinées par **Reciprocal Rank Fusion**.
- Filtres région / thème / langue avec **repli automatique** si trop peu de résultats.
- Au plus 2 passages par article ; reranker optionnel.
- **Configuration retenue** : e5 + hybride (hit@5 = 0,93, MRR = 0,79, 61 ms par question sur CPU).

### Lot 4 — Génération · [`generation/`](generation/README.md)
- Prompt avec passages numérotés, réponse dans la langue de la question.
- **Trois garde-fous contre les réponses inventées** :
  1. **périmètre** : refus des questions sur un autre pays ;
  2. **seuil de similarité** : refus sans appel au LLM si le meilleur passage est trop éloigné (cosinus < 0,82, calibré) ;
  3. **consigne `[NO_INFO]`** : le LLM doit signaler quand les passages ne contiennent pas la réponse.
- **Contrôle des citations** : suppression des numéros inventés, relance si aucune citation, alerte d'ancrage faible.
- LLM interchangeable par variables d'environnement.

### Lot 5 — Interface et évaluation · [`app.py`](app.py), [`evaluation/`](evaluation/README.md)
- Interface Streamlit avec carte de la Tunisie, choix du mode et du thème, réponse en « carte postale » avec sources.
- Jeu d'évaluation de **107 questions** (FR / EN / AR, 24 gouvernorats, 3 modes, 10 questions hors corpus).
- Comparaison des réponses **avec et sans RAG**.

---

## 4. Résultats

| Mesure (107 questions) | Résultat |
|---|---|
| Bon article dans les 5 premiers passages (hit@5, filtre région) | **1,00** |
| Bon article en première position (hit@1, mode Répondre) | 0,85 |
| Source attendue transmise au LLM | **100 %** |
| Phrases de la réponse avec une citation | **99 %** |
| Refus à tort (questions du corpus) | 2 / 71 |
| Questions hors corpus correctement refusées | **10 / 10** |
| Précision régionale des itinéraires | 0,39 *(point faible, voir §9)* |

**Avec ou sans RAG** : sans contexte, le LLM décrit des monuments qui n'existent pas (par exemple un « château du
17e siècle » à Raoued) ; avec le RAG, il reste fidèle aux sources et signale ce qu'elles ne disent pas.

Détails : [`evaluation/resultats/rapport_evaluation.md`](evaluation/resultats/rapport_evaluation.md),
[`retrieval/README.md`](retrieval/README.md), [`indexation/README.md`](indexation/README.md).

---

## 5. Installation

**Prérequis** : Python 3.10 ou 3.11, environ 3 Go d'espace disque, 8 Go de RAM conseillés.

```bash
git clone https://github.com/yomn07/HkeyetBled.git
cd HkeyetBled

python -m venv .venv
# Windows :        .venv\Scripts\activate
# Linux / macOS :  source .venv/bin/activate

python -m pip install -r requirements.txt
```
Le corpus et les index sont inclus dans le dépôt. Au premier lancement, le modèle d'embeddings e5 (~1 Go) se
télécharge automatiquement.

### Configurer le LLM

** Local avec Ollama (par défaut, gratuit)**
1. Installer Ollama : https://ollama.com/download
2. `ollama pull qwen2.5:7b-instruct`
3. Vérifier : `ollama list` affiche le modèle, et http://localhost:11434 répond « Ollama is running ».


## 6. Utilisation

### Interface web
```bash
streamlit run app.py
```
Ouvre http://localhost:8501. Choisissez un mode, éventuellement un thème ou un gouvernorat sur la carte, puis posez votre question.

**Questions d'exemple**
| Mode | Question |
|---|---|
| Répondre | « Où voir un amphithéâtre romain ? » |
| Répondre + carte (Sfax) | « Que goûter à Sfax ? » |
| Répondre (arabe) | « ما هي المدينة البونيقية المكتشفة في الوطن القبلي؟ » |
| Raconter | « Raconte-moi l'histoire de Kairouan » |
| Itinéraire | « Propose-moi un itinéraire archéologique dans le Nord » |
| Hors corpus (refus attendu) | « Quelle est la capitale du Maroc ? » |

### Ligne de commande
```bash
python -m generation.cli "Que goûter à Sfax ?" --region Sfax
python -m generation.cli "Propose-moi un itinéraire archéologique" --mode itinerary
python retrieval/retrieve.py "Où voir un amphithéâtre romain ?" --model e5   # recherche seule
```


## 7. Tests et évaluation

```bash
python -m pip install pytest
python -m pytest -q retrieval/tests             # 15 tests, sans modèle
python -m unittest discover generation/tests    # 37 tests, sans LLM
python -m pytest -q "data preprocessing/tests"  # tests du Lot 1, hors ligne

python -m evaluation.run_eval                   # retrieval, 107 questions
python -m evaluation.run_eval --no-filter       # sans filtre région (plus exigeant)
python -m evaluation.run_eval --generate        # + génération et comparaison sans RAG (LLM requis)
```

---

## 8. Structure du dépôt

```
HkeyetBled/
├── app.py                      # Interface Streamlit (Lot 5)
├── requirements.txt            # Dépendances de tout le projet
├── assets/                     # Images et fond de l'interface
├── data preprocessing/         # Lot 1 : collecte et préparation du corpus
│   ├── run_pipeline.py
│   ├── config/                 # sources, régions, thèmes, fiches rédigées par l'équipe
│   ├── data/corpus.jsonl       # ★ corpus final (1 163 documents)
│   └── docs/fiche_corpus.md    # ★ fiche de corpus
├── indexation/                 # Lot 2 : chunking, embeddings, FAISS
│   ├── index.py
│   ├── index/{e5,bge-m3,minilm}/   # ★ index prêts à l'emploi
│   └── resultats/              # comparaison des modèles
├── retrieval/                  # Lot 3 : recherche hybride
│   ├── retrieve.py
│   └── resultats/
├── generation/                 # Lot 4 : prompt, LLM, citations, refus
│   ├── pipeline.py, llm.py, prompts.py, config.py
│   └── resultats/              # calibration du seuil
└── evaluation/                 # Lot 5 : jeu de test et rapport
    ├── eval_set.jsonl
    ├── run_eval.py
    └── resultats/rapport_evaluation.md
```



## 10. Sources, licences et équipe

### Sources du corpus
| Source | Licence | Usage |
|---|---|---|
| Wikipédia FR / AR / EN, Wikivoyage | CC BY-SA 4.0 | texte complet, attribution affichée avec chaque réponse |
| UNESCO, INP, ONTT, blogs culturels | © leurs auteurs | usage pédagogique ; seul le lien figure dans `corpus_public.jsonl` |
| Fiches rédigées par l'équipe | CC BY 4.0 | expressions tunisiennes, savoir-vivre |

Le détail des sources, de la couverture et du schéma des données est dans
[`data preprocessing/docs/fiche_corpus.md`](data%20preprocessing/docs/fiche_corpus.md).

### Équipe

| Lot | Membre |
|---|---|
| 1 — Corpus et collecte | Yomn Toumia |
| 2 — Indexation | Aicha Baccour> |
| 3 — Retrieval | Hadil Boussnina |
| 4 — Génération | Ranim Latrous |
| 5 — Interface et évaluation | Zeineb Kouch |

