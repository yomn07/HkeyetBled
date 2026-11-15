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
| `resultats/comparaison_retrieval.md` | Comparaison complète : 2 modèles × 4 modes, avec et sans filtre thème |
| `resultats/details_par_question.csv` | Résultat question par question (pour l'analyse des échecs) |
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

Jeu de test : 28 questions (13 FR, 8 EN, 7 AR). hit@k = le bon article est dans les k premiers ; MRR = moyenne de 1/rang.
Les temps sont mesurés sur **CPU** (sans GPU) ; le reranker est donc nettement plus rapide sur GPU.

### Résultats globaux

| Modèle | Config | hit@1 | hit@5 | MRR | ms/question |
|---|---|---|---|---|---|
| — | bm25 | 0,571 | 0,821 | 0,685 | 238 |
| — | bm25 + filtre thème | 0,607 | 0,929 | 0,727 | 21 |
| e5 | dense | 0,679 | 0,929 | 0,766 | 87 |
| e5 | dense + filtre thème | 0,679 | 0,929 | 0,766 | 38 |
| e5 | hybrid | 0,679 | 0,929 | 0,786 | 61 |
| e5 | hybrid + filtre thème | 0,679 | 0,929 | 0,789 | 61 |
| e5 | hybrid_rerank | 0,714 | 0,929 | 0,821 | 17 653 |
| e5 | hybrid_rerank + filtre thème | 0,714 | 0,929 | 0,821 | 18 465 |
| bge-m3 | dense | 0,679 | 0,893 | 0,776 | 118 |
| bge-m3 | dense + filtre thème | 0,679 | 0,893 | 0,791 | 124 |
| bge-m3 | hybrid | 0,643 | 0,893 | 0,743 | 323 |
| bge-m3 | hybrid + filtre thème | 0,643 | 0,893 | 0,756 | 128 |
| bge-m3 | hybrid_rerank | 0,750 | 0,964 | 0,857 | 23 605 |
| bge-m3 | hybrid_rerank + filtre thème | 0,786 | 1,000 | 0,893 | 26 902 |

Détail par langue : voir `resultats/comparaison_retrieval.md`.

### Ce que montrent les résultats
- **Le reranker apporte le plus gros gain** : +0,10 de MRR avec bge-m3 (0,743 → 0,857) et +0,035 avec e5 (0,786 → 0,821). Le hit@5 de bge-m3 passe de 0,893 à 0,964.
- **L'hybride n'est pas toujours meilleur que le dense** : avec e5, léger gain de MRR (0,766 → 0,786) ; avec bge-m3, le MRR baisse (0,776 → 0,743). Les poids `w_dense` / `w_bm25` n'ont pas encore été réglés.
- **bge-m3 est le meilleur en arabe avec le reranker** : hit@1 = 0,857 et MRR = 0,929 (7 questions), contre 0,714 et 0,786 pour e5.
- **Le filtre thème est un cas idéal** : dans `evaluate.py`, le thème est lu directement dans `questions_test.jsonl`. En usage réel, l'utilisateur ne fournit pas le thème. Les lignes « + filtre thème » (en particulier hit@5 = 1,0) sont donc un plafond ; pour comparer honnêtement les configurations, on utilise les lignes **sans** filtre.

### Configuration recommandée
| Cas | Configuration | Résultats (sans filtre thème) |
|---|---|---|
| Qualité maximale | **bge-m3 + hybrid + reranker** | hit@5 = 0,964 ; MRR = 0,857 ; très lent sur CPU (~24 s/question), à utiliser avec un GPU |
| Rapide / démo sans GPU | **e5 + hybrid** (défaut de `retrieve()`) | hit@5 = 0,929 ; MRR = 0,786 ; 61 ms/question |

Choix du modèle : bge-m3 si l'arabe compte (meilleur MRR après reranking, hit@5 = 1,0 en arabe) ; e5 s'il faut un modèle plus léger (index de 26 Mo contre 35 Mo, indexation 2,4 fois plus rapide).

## Reste à faire
1. Régler `w_dense`, `w_bm25` et `pool` (en particulier pour bge-m3, où l'hybride fait moins bien que le dense seul).
2. Analyser les questions encore ratées avec la configuration retenue (`resultats/details_par_question.csv`) : à présenter à la soutenance.
3. Si le filtre thème est utilisé en production, prévoir une classification automatique du thème de la question.

## Limites connues
- Le jeu de test est petit (28 questions) : une question de plus ou de moins change le hit@5 d'environ 3,6 points ; les écarts de l'ordre de 0,03 entre configurations ne sont pas significatifs.
- Le filtre thème de l'évaluation utilise le thème fourni dans le jeu de test (cas idéal), pas un thème prédit.
- Le filtre région dépend de l'annotation du Lot 1 (lexique de lieux), qui peut se tromper.
- Les cases région × thème peu fournies (ex. artisanat) peuvent renvoyer peu de résultats : le repli compense.
- Le reranker `BAAI/bge-reranker-v2-m3` est lourd ; mesuré sur CPU : 17 à 27 secondes par question. Un GPU est conseillé.
