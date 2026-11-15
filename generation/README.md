# Lot 4 — Génération (Hkeyet Bled RAG)

## En une phrase
Reçoit une **question**, appelle le Lot 3 (`retrieve`), construit un prompt avec les passages numérotés,
interroge un LLM et renvoie une **réponse citée + la liste des sources** — ou un **refus** si le corpus ne sait pas.

## Installation
Copier le dossier `generation/` **à la racine du dépôt**, à côté de `retrieval/` et `indexation/`.
Aucune dépendance de plus (`requests` est déjà dans `requirements.txt`).

## Choisir le LLM (variables d'environnement)
| Cas | Commandes |
|---|---|
| Local (Ollama, défaut) | `ollama pull qwen2.5:7b-instruct` |
| API compatible OpenAI (OpenAI, Groq, Mistral…) | `LLM_PROVIDER=openai LLM_API_KEY=… LLM_MODEL=<modèle> [LLM_BASE_URL=<url>]` |
| API Anthropic | `LLM_PROVIDER=anthropic LLM_API_KEY=… [LLM_MODEL=<modèle>]` |

Windows (cmd) : `set LLM_PROVIDER=openai` — PowerShell : `$env:LLM_PROVIDER="openai"`.

## Utilisation
```
python -m generation.cli "Que goûter à Sfax ?" --region Sfax
python -m generation.cli "Propose-moi un itinéraire archéologique" --mode itinerary
python -m generation.cli "ما هي المدينة البونيقية المكتشفة في الوطن القبلي؟"
python -m generation.cli "Que visiter à Kairouan ?" --mock        # sans index ni modèle
```
Depuis du code Python (Lot 5, interface) :
```python
from generation import rag_answer
from generation.retriever_adapter import make_retriever
retrieve = make_retriever()                       # e5 + hybride (RAG_MODEL, RAG_MODE pour changer)
r = rag_answer("Que goûter à Sfax ?", retrieve, filters={"region": "Sfax"}, mode="auto")
```
`r` contient : `answer`, `sources` (titre, section, url, licence, région, thème, langue, `text`, `cited`),
`mode`, `lang`, `refused`, `reason` (`no_relevant_passage` | `llm_no_info`), `warnings`, `n_retrieved`, `n_used`,
`best_relevance`. Les `text` des sources servent de `contexts` pour RAGAS.

## Ce que le Lot 4 reprend des lots précédents
| Venant de | Utilisé pour |
|---|---|
| Lot 3 `retrieve()` | passages triés, `dense_score` (cosinus) pour le refus, `repli` pour prévenir l'utilisateur |
| Lot 2 (chunks) | `title`, `section`, `lang`, `region` mis dans le contexte ; chunks ≤ ~1900 caractères |
| Lot 1 (corpus) | `url` + `license` affichés avec chaque source (CC BY-SA : attribution obligatoire) ; thèmes et régions dans `constants.py` |

## Décisions importantes
- **Trois garde-fous contre les réponses hors corpus**, dans cet ordre :
  0. **Périmètre** : une question qui cite un pays étranger sans citer la Tunisie est refusée sans recherche (`reason=out_of_scope`). Liste de pays simple, donc best-effort.
  1. **Seuil de similarité** : le meilleur `dense_score` (cosinus) doit atteindre `RAG_MIN_SCORE`, sinon refus sans appel au LLM (`no_relevant_passage`).
  2. **LLM** : le prompt exige `[NO_INFO]` si la réponse n'est pas dans les passages (`llm_no_info`).
- **Seuil sur le cosinus, pas sur `score`** : en mode hybride, `score` est un score RRF (≤ 0,033), sans rapport avec un seuil.
- **Seuil e5 = 0,82, mesuré** (`python -m generation.calibrate --model e5`) : aucune des 37 questions du corpus n'est refusée, mais les groupes se chevauchent (Maroc 0,837, Algérie 0,835 contre 0,825 pour la question du corpus la plus basse), d'où les garde-fous 0 et 2. Les seuils bge-m3 et minilm ne sont pas calibrés.
- **Mode bm25 seul** : pas de cosinus, donc pas de seuil.
- **Citations contrôlées** : numéros inventés supprimés ; résidu `[1] [2]…` en tête de réponse retiré ; une relance automatique si aucune citation ou si la couverture est trop faible (`citation_retry`, `low_citation_coverage`).
- **Ancrage lexical** (`grounding`, `weak_grounding`) : alerte quand les mots distinctifs de la réponse ne figurent pas dans les passages cités. Jamais un refus automatique ; non calculé pour l'arabe.
- **Nombre de passages selon le mode** : réponse 5, récit 6, itinéraire 8 (`RAG_TOP_K` force une valeur).
- **Corpus multilingue** : le prompt demande de traduire fidèlement et de répondre dans la langue de la question (fr/en/ar).
- **Repli du Lot 3** : si le filtre région/thème a été assoupli, une note est ajoutée au prompt (`warnings=["filtre_assoupli"]`).

## Paramètres
`RAG_MODEL` (e5), `RAG_MODE` (hybrid), `RAG_RERANK` (0), `RAG_MIN_SCORE`, `RAG_TOP_K`, `RAG_MAX_CHARS_PASSAGE` (2000),
`RAG_MAX_CONTEXT_CHARS` (12000), `LLM_TEMPERATURE` (0,2).

## Tests
```
python -m unittest discover generation/tests -v
```
37 tests, sans LLM ni modèle d'embeddings (dont des non-régressions sur le seuil RRF/cosinus, les citations et le périmètre).

## À faire pour terminer le lot
1. Lancer `python -m generation.cli` avec le vrai LLM sur les 3 modes et les 3 langues.
2. Lancer `python -m generation.calibrate --model <modèle retenu par le Lot 3>` et fixer `RAG_MIN_SCORE`.
3. Ajouter 2 ou 3 questions hors corpus dans `calibrate.py` (`OFF_TOPIC`) : ce sont les cas de refus de la soutenance.
4. Comparer 2 LLM (ex. Ollama et une API) sur 5 questions et noter qualité, citations, latence.

## Limites connues
- Un petit LLM (3b) peut répondre depuis ses propres connaissances et citer des sources sans rapport : constaté sur « capitale de l'Algérie » avant l'ajout du garde-fou de périmètre. Un modèle plus fort réduit ce risque ; `weak_grounding` le signale.
- Une question hors sujet proche du corpus et sans pays cité n'est arrêtée que par le seuil (0,82) et par le LLM.
- Le seuil dépend du modèle d'embeddings : changer de modèle impose de recalibrer.
- Un LLM local de 7B peut oublier les citations ou le tag `[NO_INFO]` ; `warnings` le signale.
- Les questions descriptives sans nom de lieu restent difficiles pour le Lot 3 (cf. rapport du Lot 2) ; le Lot 4 ne peut pas répondre mieux que les passages reçus.
