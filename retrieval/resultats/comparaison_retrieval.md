# Lot 3 — Comparaison des configurations de retrieval

28 questions de test (FR/AR/EN). hit@k = bon article dans les k premiers ; MRR = moyenne de 1/rang.

## Résultats globaux

| modèle | config | n | hit@1 | hit@5 | MRR | ms/question |
|---|---|---|---|---|---|---|
| — | bm25 | 28 | 0.571 | 0.821 | 0.685 | 238 |
| — | bm25+filtre_theme | 28 | 0.607 | 0.929 | 0.727 | 21 |
| e5 | dense | 28 | 0.679 | 0.929 | 0.766 | 87 |
| e5 | dense+filtre_theme | 28 | 0.679 | 0.929 | 0.766 | 38 |
| e5 | hybrid | 28 | 0.679 | 0.929 | 0.786 | 61 |
| e5 | hybrid+filtre_theme | 28 | 0.679 | 0.929 | 0.789 | 61 |
| e5 | hybrid_rerank | 28 | 0.714 | 0.929 | 0.821 | 17653 |
| e5 | hybrid_rerank+filtre_theme | 28 | 0.714 | 0.929 | 0.821 | 18465 |
| bge-m3 | dense | 28 | 0.679 | 0.893 | 0.776 | 118 |
| bge-m3 | dense+filtre_theme | 28 | 0.679 | 0.893 | 0.791 | 124 |
| bge-m3 | hybrid | 28 | 0.643 | 0.893 | 0.743 | 323 |
| bge-m3 | hybrid+filtre_theme | 28 | 0.643 | 0.893 | 0.756 | 128 |
| bge-m3 | hybrid_rerank | 28 | 0.75 | 0.964 | 0.857 | 23605 |
| bge-m3 | hybrid_rerank+filtre_theme | 28 | 0.786 | 1.0 | 0.893 | 26902 |


## Par langue

| modèle | config | langue | n | hit@1 | hit@5 | MRR |
|---|---|---|---|---|---|---|
| — | bm25 | ar | 7 | 0.571 | 0.714 | 0.667 |
| — | bm25 | en | 8 | 0.625 | 1.0 | 0.781 |
| — | bm25 | fr | 13 | 0.538 | 0.769 | 0.635 |
| — | bm25+filtre_theme | ar | 7 | 0.571 | 0.857 | 0.679 |
| — | bm25+filtre_theme | en | 8 | 0.625 | 1.0 | 0.781 |
| — | bm25+filtre_theme | fr | 13 | 0.615 | 0.923 | 0.721 |
| e5 | dense | ar | 7 | 0.857 | 0.857 | 0.857 |
| e5 | dense | en | 8 | 0.625 | 1.0 | 0.744 |
| e5 | dense | fr | 13 | 0.615 | 0.923 | 0.731 |
| e5 | dense+filtre_theme | ar | 7 | 0.857 | 0.857 | 0.857 |
| e5 | dense+filtre_theme | en | 8 | 0.625 | 1.0 | 0.744 |
| e5 | dense+filtre_theme | fr | 13 | 0.615 | 0.923 | 0.731 |
| e5 | hybrid | ar | 7 | 0.714 | 0.857 | 0.786 |
| e5 | hybrid | en | 8 | 0.625 | 1.0 | 0.781 |
| e5 | hybrid | fr | 13 | 0.692 | 0.923 | 0.788 |
| e5 | hybrid+filtre_theme | ar | 7 | 0.714 | 0.857 | 0.786 |
| e5 | hybrid+filtre_theme | en | 8 | 0.625 | 1.0 | 0.781 |
| e5 | hybrid+filtre_theme | fr | 13 | 0.692 | 0.923 | 0.795 |
| e5 | hybrid_rerank | ar | 7 | 0.714 | 0.857 | 0.786 |
| e5 | hybrid_rerank | en | 8 | 0.75 | 1.0 | 0.875 |
| e5 | hybrid_rerank | fr | 13 | 0.692 | 0.923 | 0.808 |
| e5 | hybrid_rerank+filtre_theme | ar | 7 | 0.714 | 0.857 | 0.786 |
| e5 | hybrid_rerank+filtre_theme | en | 8 | 0.75 | 1.0 | 0.875 |
| e5 | hybrid_rerank+filtre_theme | fr | 13 | 0.692 | 0.923 | 0.808 |
| bge-m3 | dense | ar | 7 | 0.571 | 1.0 | 0.75 |
| bge-m3 | dense | en | 8 | 0.75 | 0.875 | 0.83 |
| bge-m3 | dense | fr | 13 | 0.692 | 0.846 | 0.756 |
| bge-m3 | dense+filtre_theme | ar | 7 | 0.571 | 1.0 | 0.786 |
| bge-m3 | dense+filtre_theme | en | 8 | 0.75 | 0.875 | 0.83 |
| bge-m3 | dense+filtre_theme | fr | 13 | 0.692 | 0.846 | 0.769 |
| bge-m3 | hybrid | ar | 7 | 0.571 | 0.857 | 0.714 |
| bge-m3 | hybrid | en | 8 | 0.75 | 1.0 | 0.806 |
| bge-m3 | hybrid | fr | 13 | 0.615 | 0.846 | 0.719 |
| bge-m3 | hybrid+filtre_theme | ar | 7 | 0.571 | 0.857 | 0.73 |
| bge-m3 | hybrid+filtre_theme | en | 8 | 0.75 | 1.0 | 0.806 |
| bge-m3 | hybrid+filtre_theme | fr | 13 | 0.615 | 0.846 | 0.738 |
| bge-m3 | hybrid_rerank | ar | 7 | 0.857 | 1.0 | 0.929 |
| bge-m3 | hybrid_rerank | en | 8 | 0.75 | 1.0 | 0.875 |
| bge-m3 | hybrid_rerank | fr | 13 | 0.692 | 0.923 | 0.808 |
| bge-m3 | hybrid_rerank+filtre_theme | ar | 7 | 0.857 | 1.0 | 0.929 |
| bge-m3 | hybrid_rerank+filtre_theme | en | 8 | 0.75 | 1.0 | 0.875 |
| bge-m3 | hybrid_rerank+filtre_theme | fr | 13 | 0.769 | 1.0 | 0.885 |
