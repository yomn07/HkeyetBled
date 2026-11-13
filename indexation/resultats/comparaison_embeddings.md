## Comparaison globale (28 questions)

| modele | dim | chunks | materiel | temps_index_s | taille_index_mo | hit@5 | MRR | ms_par_requete |
|---|---|---|---|---|---|---|---|---|
| e5 | 768 | 8474 | cuda:0 (fp16) | 57.6 | 26.03 | 0.893 | 0.738 | 27.7 |
| bge-m3 | 1024 | 8474 | cuda:0 (fp16) | 138.0 | 34.71 | 0.893 | 0.771 | 26.2 |
| minilm | 384 | 8474 | cuda:0 (fp16) | 38.2 | 13.02 | 0.607 | 0.458 | 12.9 |

## Par langue de la question

| modele | langue | questions | hit@5 | MRR |
|---|---|---|---|---|
| e5 | ar | 7 | 0.857 | 0.857 |
| e5 | en | 8 | 0.875 | 0.719 |
| e5 | fr | 13 | 0.923 | 0.686 |
| bge-m3 | ar | 7 | 1.0 | 0.75 |
| bge-m3 | en | 8 | 0.875 | 0.812 |
| bge-m3 | fr | 13 | 0.846 | 0.756 |
| minilm | ar | 7 | 0.286 | 0.119 |
| minilm | en | 8 | 0.75 | 0.75 |
| minilm | fr | 13 | 0.692 | 0.462 |
