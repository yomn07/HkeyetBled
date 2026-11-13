# Lot 3 — Comparaison des configurations de retrieval

28 questions de test (FR/AR/EN). hit@k = bon article dans les k premiers ; MRR = moyenne de 1/rang.

## Résultats globaux

| modèle | config | n | hit@1 | hit@5 | MRR | ms/question |
|---|---|---|---|---|---|---|
| — | bm25 | 28 | 0.571 | 0.821 | 0.685 | 80 |


## Par langue

| modèle | config | langue | n | hit@1 | hit@5 | MRR |
|---|---|---|---|---|---|---|
| — | bm25 | ar | 7 | 0.571 | 0.714 | 0.667 |
| — | bm25 | en | 8 | 0.625 | 1.0 | 0.781 |
| — | bm25 | fr | 13 | 0.538 | 0.769 | 0.635 |
