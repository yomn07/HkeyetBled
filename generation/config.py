"""Paramètres du lot Génération, modifiables par variables d'environnement."""
import os
from dataclasses import dataclass
from typing import Optional

# provider -> (modèle par défaut, URL de base par défaut)
_DEFAULTS = {
    "ollama": ("qwen2.5:7b-instruct", "http://localhost:11434"),
    # "openai" = tout service compatible OpenAI (OpenAI, Groq, Mistral, Together...)
    "openai": ("gpt-4o-mini", "https://api.openai.com/v1"),
    "anthropic": ("claude-sonnet-5-5", "https://api.anthropic.com"),
}

# Seuil de refus sur le COSINUS (dense_score) du meilleur passage, par modèle d'embeddings.
# e5 : CALIBRÉ (37 questions du corpus, 16 hors sujet) -> 0.82 = aucun faux refus mesuré
#      (voir generation/resultats/calibration_seuil_e5.md ; les cas proches du sujet comme
#      "capitale de l'Algérie" sont arrêtés par le garde-fou de périmètre et par le LLM).
# bge-m3 et minilm : valeurs de départ NON calibrées -> python -m generation.calibrate --model <nom>
DEFAULT_MIN_DENSE = {"e5": 0.82, "bge-m3": 0.40, "minilm": 0.30}


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: int
    top_k: Optional[int]          # None = valeur par défaut selon le mode
    rag_model: str                # index du Lot 2 : e5 | bge-m3 | minilm
    rag_mode: str                 # recherche du Lot 3 : hybrid | dense | bm25
    rag_rerank: bool
    min_score: float
    max_chars_per_passage: int
    max_context_chars: int


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider not in _DEFAULTS:
        raise ValueError(
            f"LLM_PROVIDER inconnu : {provider!r} (choix : {', '.join(_DEFAULTS)})"
        )
    model, base_url = _DEFAULTS[provider]
    rag_model = os.getenv("RAG_MODEL", "e5")
    top_k = os.getenv("RAG_TOP_K")
    return Settings(
        provider=provider,
        model=os.getenv("LLM_MODEL", model),
        base_url=os.getenv("LLM_BASE_URL", base_url).rstrip("/"),
        api_key=os.getenv("LLM_API_KEY", ""),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "700")),
        timeout=int(os.getenv("LLM_TIMEOUT", "120")),
        top_k=int(top_k) if top_k else None,
        rag_model=rag_model,
        rag_mode=os.getenv("RAG_MODE", "hybrid"),
        rag_rerank=os.getenv("RAG_RERANK", "0") == "1",
        min_score=float(os.getenv("RAG_MIN_SCORE", DEFAULT_MIN_DENSE.get(rag_model, 0.5))),
        # un chunk fait au plus ~1900 caractères (400 tokens), 890 en moyenne
        max_chars_per_passage=int(os.getenv("RAG_MAX_CHARS_PASSAGE", "2000")),
        max_context_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000")),
    )
