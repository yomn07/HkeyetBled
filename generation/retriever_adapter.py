"""Branche le module retrieve() du Lot 3 sur le pipeline de génération.

Le Lot 3 expose  retrieve(question, k, region, theme, lang, model, mode, rerank).
Le pipeline attend  f(question, filters, k) -> passages.
À lancer depuis la RACINE du dépôt (à côté de retrieval/ et indexation/).
"""
from .config import get_settings


def make_retriever(model=None, mode=None, rerank=None):
    s = get_settings()
    model = model or s.rag_model
    mode = mode or s.rag_mode
    rerank = s.rag_rerank if rerank is None else rerank

    def _retrieve(question, filters=None, k=5):
        from retrieval.retrieve import retrieve  # import tardif : charge le modèle au 1er appel

        f = filters or {}
        return retrieve(
            question, k=k, region=f.get("region"), theme=f.get("theme"), lang=f.get("lang"),
            model=model, mode=mode, rerank=rerank,
        )

    return _retrieve
