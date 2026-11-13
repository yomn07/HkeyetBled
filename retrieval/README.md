# Lot 3 — Retrieval (Hkeyet Bled RAG)

## En une phrase
Ce module reçoit une **question** et renvoie les **5 passages (chunks) les plus utiles** au Lot 4 (génération).
Analogie : c'est le bibliothécaire. Le Lot 2 a rangé les 8 474 fiches ; ici on les retrouve.

## Comment il cherche
| Étape | Ce qui se passe | Pourquoi |
|---|---|---|
| 1. Filtres (option) | On garde les chunks de la bonne région / thème / langue, plus ceux de région « National » | « Djerba » ne doit pas renvoyer Tozeur |
| 2. Recherche **dense** | La question devient un vecteur ; on prend les chunks de sens proche (index du Lot 2) | Comprend les reformulations et les langues |
| 3. Recherche **BM25** | On compte les mots communs (titre compté double ; accents et variantes arabes normalisés) | Retrouve les noms propres (« Kerkouane ») |
| 4. Fusion **RRF** | On combine les deux classements : `score = 1/(60+rang)` | Un chunk bien classé par les deux gagne |
| 5. Reranker (option) | Un second modèle relit les 30 meilleurs et les reclasse | Plus précis, mais plus lent |
| 6. Dédoublonnage | Au plus 2 chunks par article (traductions incluses, via `group_id`) | Évite 5 fois le même texte |
| 7. Repli | Si le filtre laisse moins de k résultats, on l'assouplit : langue, puis thème, puis région | Évite les réponses vides |

## Contenu du dossier
| Fichier | Rôle |
|---|---|
| `retrieve.py` | Le module : `retrieve(question, ...)`, `to_context(...)`, classe `Retriever` |
| `evaluate.py` | Compare bm25 / dense / hybride / reranker sur les 28 questions |
| `tests/test_retrieval.py` | 15 tests sans modèle ni GPU |
| `resultats/baseline_bm25.md` | Résultats mesurés pour BM25 seul |
| `requirements.txt` | `numpy`, `rank_bm25` |

## Installation
Dézipper **à la racine du dépôt**, à côté de `indexation/` (le module lit `indexation/index/<modèle>/`).
```
pip install -r retrieval/requirements.txt
```
Il faut aussi `faiss-cpu`, `sentence-transformers` et `torch` (déjà utilisés au Lot 2).

## Utilisation
```
python retrieval/retrieve.py "Où voir un amphithéâtre romain ?" --model e5
python retrieval/retrieve.py "Que goûter à Sfax ?" --region Sfax --theme gastronomie
python retrieval/retrieve.py "Quel est le plus haut sommet de Tunisie ?" --mode bm25 --k 3
```
Depuis le Lot 4 :
```python
from retrieval.retrieve import retrieve, to_context
passages = retrieve("Que goûter à Sfax ?", region="Sfax", k=5)   # modèle e5, mode hybride
prompt_contexte = to_context(passages)                            # texte numéroté [1], [2]… avec URL et licence
```

## Contrat avec le Lot 4
`retrieve(...)` renvoie une liste de dictionnaires triés. Chaque élément contient tous les champs du chunk
(`chunk_id`, `doc_id`, `title`, `section`, `text`, `lang`, `url`, `source`, `license`, `redistributable`,
`region`, `theme`, `group_id`, …) plus : `rank`, `score`, `mode`, `dense_score`, `bm25_score`,
`filtre` (filtre réellement appliqué) et `repli` (True si le filtre a été assoupli).

## Évaluation
```
python retrieval/evaluate.py --models e5 bge-m3 --modes bm25 dense hybrid hybrid_rerank --theme-filter
```
Écrit `resultats/comparaison_retrieval.md` et `details_par_question.csv`.

**Mesuré ici (BM25 seul, 28 questions)** : hit@1 = 0,571 ; hit@5 = 0,821 ; MRR = 0,685.
Rappel du Lot 2 (dense seul) : hit@5 = 0,893 avec e5 et bge-m3.
Les lignes dense, hybride et reranker sont **à produire** en lançant la commande ci-dessus (modèles requis, GPU conseillé).

## À faire pour terminer le lot
1. Lancer `evaluate.py` avec les 4 modes et les 2 modèles ; coller le tableau dans le rapport.
2. Choisir le modèle d'embeddings final (e5 plus léger, bge-m3 meilleur en arabe) et le justifier avec les chiffres.
3. Garder le reranker seulement si le gain de hit@5 / MRR justifie le temps de réponse.
4. Régler `w_dense`, `w_bm25`, `pool` si l'hybride ne dépasse pas le dense seul.
5. Analyser les questions encore ratées (`details_par_question.csv`) : à présenter à la soutenance.

## Limites connues
- Le jeu de test est petit (28 questions) : une question de plus ou de moins change le hit@5 d'environ 3,6 points.
- Le filtre région dépend de l'annotation du Lot 1 (lexique de lieux), qui peut se tromper.
- Les cases région × thème peu fournies (ex. artisanat) peuvent renvoyer peu de résultats : le repli compense.
- Le reranker `BAAI/bge-reranker-v2-m3` est lourd ; sur CPU, comptez plusieurs secondes par question.
