# Hkeyet Bled RAG — Lot 2 : Indexation

Ce dossier transforme le corpus du Lot 1 (`data preprocessing/data/corpus.jsonl`) en **index vectoriel** interrogeable :
**chunking → embeddings multilingues → index FAISS + métadonnées.**

Livrables du lot : les index des trois modèles dans `index/` (prêts à l'emploi), le script `index.py` qui les reconstruit en une commande, et les résultats de la comparaison des modèles dans `resultats/`.

**Pour le Lot 3 :** les index sont dans Git, il n'y a rien à reconstruire. Après un `git pull`, `python indexation/index.py search --model e5 "…"` fonctionne directement (le modèle d'embeddings se télécharge automatiquement la première fois).

---

## 1. Reproduire le Lot 2 de zéro (nouvel ordinateur)

Les commandes ci-dessous sont pour l'invite de commandes Windows (cmd). Sous Linux ou Mac, remplacez les `\` par des `/` et activez l'environnement avec `source .venv/bin/activate`.

**Étape 1 — Récupérer le dépôt et la branche du Lot 2**

```cmd
git clone <lien du dépôt>
cd HkeyetBled
git checkout indexation
```

La branche contient aussi tout le travail du Lot 1 (dossier `data preprocessing`), car elle a été créée à partir de `main`.

**Étape 2 — Installer l'environnement**

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10 ou plus récent. Sur une machine avec GPU NVIDIA, remplacez PyTorch par sa version CUDA (commande donnée sur pytorch.org) pour accélérer l'encodage. Le script utilise automatiquement le GPU s'il est disponible, en demi-précision (fp16), et revient sur le CPU si la mémoire GPU ne suffit pas.

**Étape 3 — Vérifier que le corpus du Lot 1 est présent**

Le Lot 2 n'a besoin que d'un seul fichier du Lot 1 : `data preprocessing/data/corpus.jsonl`. Il est versionné dans Git, donc normalement déjà là :

```cmd
dir "data preprocessing\data\corpus.jsonl"
```

S'il manque, il faut le régénérer avec le pipeline du Lot 1 (20 à 30 minutes, connexion internet nécessaire). Mettez d'abord une adresse e-mail de contact dans `data preprocessing/config/sources.yaml` (`http.user_agent`), puis :

```cmd
cd "data preprocessing"
python run_pipeline.py all
cd ..
```

Le corpus régénéré peut différer légèrement de celui du Lot 1, car Wikipédia et les sites web changent avec le temps. Lors de notre reproduction, nous avons obtenu **1 160 documents contre 1 163** pour la version du Lot 1. Pour que toute l'équipe travaille sur les mêmes données, utilisez de préférence le corpus versionné.

**Étape 4 — Construire l'index**

Cette étape est facultative : les index des trois modèles sont déjà dans le dépôt (`indexation/index/`). Reconstruisez-les seulement si le corpus a changé ou pour vérifier la méthode.

```cmd
python indexation\index.py build --model e5
```

Durée de l'encodage : environ 45 minutes sur le CPU d'un portable, moins d'une minute sur un GPU Tesla T4 (Google Colab gratuit). Sur un petit GPU de 2 Go, ajoutez `--batch-size 8`.

Pour un test rapide sur 20 documents : ajoutez `--limit 20`.

**Étape 5 — Tester une recherche**

```cmd
python indexation\index.py search --model e5 "Où voir un amphithéâtre romain ?"
```

L'article sur l'amphithéâtre d'El Jem doit arriver en tête.

**Étape 6 — Refaire la comparaison des modèles**

```cmd
python indexation\index.py compare --models e5 bge-m3 minilm --questions indexation\questions_test.jsonl
```

Les index manquants sont construits automatiquement. Les tableaux sont écrits dans `indexation/resultats/`. bge-m3 (2,2 Go) ne tient pas sur un GPU de 2 Go : utilisez Colab ou le CPU.

### Avec Google Colab (recommandé sans bon GPU)

1. Dans Colab : *Exécution → Modifier le type d'exécution → GPU T4*.
2. Compressez les dossiers `data preprocessing` et `indexation` en un zip (sans `.venv`), puis importez-le dans Colab et décompressez-le dans `/content/HkeyetBled`.
3. `!pip install -q faiss-cpu sentence-transformers`
4. `%cd /content/HkeyetBled` puis lancez les commandes des étapes 4 à 6 précédées de `!`.
5. Téléchargez les dossiers `indexation/index` et `indexation/resultats` (zip) avant la fin de la session, puis décompressez-les à la racine du dépôt sur votre ordinateur.

### Lien entre l'index et le corpus

Chaque `config.json` enregistre une empreinte du corpus utilisé (`corpus_sha256`). Si le Lot 1 publie un nouveau `corpus.jsonl`, l'empreinte ne correspond plus : il faut reconstruire l'index avec l'étape 4.

## 2. Commandes (résumé)

Toutes les commandes se lancent depuis la racine du dépôt.

| Commande | Effet |
|---|---|
| `python indexation/index.py build --model e5` | construit l'index e5 sur tout le corpus |
| `python indexation/index.py build --model e5 --limit 20` | test rapide sur 20 documents |
| `python indexation/index.py search --model e5 "Où voir un amphithéâtre romain ?"` | recherche top-5 |
| `python indexation/index.py search --model e5 "couscous" --region Sfax --theme gastronomie` | recherche avec filtres |
| `python indexation/index.py compare --models e5 bge-m3 minilm --questions indexation/questions_test.jsonl` | compare les modèles |

Options utiles : `--batch-size` (réduire à 8 ou 16 sur un petit GPU), `--max-tokens`, `--overlap`, `--k`.

## 3. Ce que produit le script

```
indexation/
  index.py                  # script de construction, recherche et comparaison
  questions_test.jsonl      # 28 questions de test (FR / AR / EN)
  resultats/
    comparaison_embeddings.md   # tableaux de comparaison (global + par langue)
    comparaison_details.csv     # rang du bon document pour chaque modèle et chaque question
  index/                    # un dossier par modèle (e5, bge-m3, minilm) :
    e5/
      index.faiss           # vecteurs normalisés (produit scalaire = similarité cosinus)
      chunks.jsonl          # texte + métadonnées, une ligne par chunk, même ordre que l'index
      config.json           # modèle, chunking, temps d'indexation, taille, matériel
```

### Format d'un chunk (contrat avec les Lots 3 et 4)

```json
{"chunk_id": "wikipedia_fr_amphitheatre-d-el-jem_b24529__003", "doc_id": "wikipedia_fr_amphitheatre-d-el-jem_b24529",
 "section": "Histoire", "text": "…", "n_tokens": 312,
 "title": "Amphithéâtre d'El Jem", "lang": "fr", "url": "https://fr.wikipedia.org/…",
 "source": "wikipedia", "license": "CC BY-SA 4.0", "region": "Mahdia", "regions": ["Mahdia"],
 "theme": "patrimoine_archeologique", "themes": ["patrimoine_archeologique"], "group_id": "g_…"}
```

À savoir pour le **Lot 3** :
- la ligne *i* de `chunks.jsonl` décrit le vecteur *i* de `index.faiss` ;
- avec e5, chaque question doit commencer par `"query: "` (la classe `Index` du script le fait via `config.json`) ;
- la classe `Index` fait déjà la recherche top-k avec filtres région / thème / langue : point de départ pour BM25 et le reranker.

## 4. Méthode (à présenter à la soutenance)

1. **Chunking** : on coupe d'abord aux sections `## Titre` du Lot 1 (une section = un sujet). Une section de plus de 400 tokens est découpée en fenêtres de 400 tokens avec **80 tokens de chevauchement**, pour qu'une phrase coupée se retrouve entière dans le chunk suivant. Les sections de moins de 60 tokens sont collées à la suivante. Résultat : 1 163 documents → **8 474 chunks**, 242 tokens en moyenne.
2. **Contexte** : le titre du document et le nom de la section sont ajoutés en tête du texte encodé, car un chunk pris au milieu d'un article ne nomme pas forcément son sujet.
3. **Embeddings** : trois modèles multilingues pré-entraînés (aucun entraînement, seulement l'encodage du corpus) : `intfloat/multilingual-e5-base`, `BAAI/bge-m3`, `paraphrase-multilingual-MiniLM-L12-v2`. Vecteurs normalisés.
4. **Index** : FAISS `IndexFlatIP`, recherche exacte par similarité cosinus, assez rapide pour quelques milliers de chunks.
5. **Évaluation** : 28 questions en FR / AR / EN sur les 9 thèmes, dont des questions posées dans une langue alors que la réponse est dans une autre. Une question est réussie si le bon document (dans l'une de ses langues) est dans les 5 premiers résultats. Mesures : hit@5, MRR et temps par requête.

## 5. Résultats

### Comparaison des modèles (28 questions, GPU Tesla T4, fp16)

| Modèle | Dim. | Temps d'indexation | Taille de l'index | hit@5 | MRR | ms / requête |
|---|---|---|---|---|---|---|
| e5 | 768 | 57,6 s | 26,0 Mo | 0,893 | 0,738 | 27,7 |
| bge-m3 | 1024 | 138,0 s | 34,7 Mo | 0,893 | 0,771 | 26,2 |
| MiniLM | 384 | 38,2 s | 13,0 Mo | 0,607 | 0,458 | 12,9 |

### Par langue de la question (hit@5)

| Modèle | Arabe (7) | Anglais (8) | Français (13) |
|---|---|---|---|
| e5 | 0,857 | 0,875 | 0,923 |
| bge-m3 | 1,0 | 0,875 | 0,846 |
| MiniLM | 0,286 | 0,75 | 0,692 |

### Temps d'encodage selon le matériel (e5, mêmes paramètres)

| Matériel | Corpus | Temps des embeddings |
|---|---|---|
| CPU portable | 50 documents (325 chunks) | 106,5 s |
| GPU portable GeForce MX550, 2 Go (fp16) | 50 documents (325 chunks) | 95,9 s |
| GPU Colab Tesla T4, 15 Go (fp16) | 1 163 documents (8 474 chunks) | 42,5 s |

Le petit GPU portable n'apporte presque rien (moins de 10 %) : il manque de mémoire et n'a pas de cœurs spécialisés pour le fp16. bge-m3 (2,2 Go) ne tient pas dans ses 2 Go.

### Analyse

- **e5 et bge-m3 sont équivalents en qualité** sur ce jeu de test : même hit@5, et l'écart de MRR (0,03) correspond à environ une question classée 1re au lieu de 2e. Avec 28 questions, cette différence n'est pas significative.
- **bge-m3 est le meilleur en arabe** (7 / 7), mais il est 2,4 fois plus long à indexer, son index est 33 % plus gros et le modèle est deux fois plus lourd.
- **MiniLM est écarté** : il échoue sur la plupart des questions en arabe.
- **Erreurs communes à e5 et bge-m3** : des questions descriptives qui ne nomment pas le lieu (« oasis de montagne près de Tozeur » pour Chebika, « zone humide près de Sousse » pour Sebkha Kelbia). Le modèle renvoie alors l'article de la ville voisine, qui mentionne souvent le site. L'évaluation par titre est donc stricte.
- **Remarque pour le Lot 1** : un document intitulé « catalogue » remonte pour une question sur Sousse ; son titre d'origine a probablement été perdu au nettoyage.

### Modèle retenu

**Choix reporté au Lot 3** : les trois index sont fournis dans le dépôt, et le Membre 3 les compare dans le module de retrieval (recherche hybride BM25 + dense, reranker). e5 et bge-m3 sont les deux candidats ; MiniLM est écarté à cause de ses résultats en arabe. Critère pratique : e5 si la démo tourne sur des ordinateurs portables sans GPU puissant (deux fois plus léger, même qualité), bge-m3 si elle tourne sur un serveur ou Colab avec GPU.

## 6. Checklist du Lot 2

- [x] Chunking défini (400 tokens, chevauchement 80, coupe par sections)
- [x] 3 modèles d'embeddings comparés (e5, bge-m3, MiniLM)
- [x] Vecteurs stockés avec leurs métadonnées (`chunks.jsonl`)
- [x] Index FAISS construit et sauvegardé, script de reconstruction
- [x] Temps d'indexation et taille de l'index mesurés
- [x] Index des trois modèles partagés avec le Membre 3 (dans le dépôt)
- [ ] Modèle retenu choisi avec le Lot 3