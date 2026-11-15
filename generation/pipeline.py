"""Pipeline retrieval -> génération (lot 4).

Contrat avec le Lot 3 (adapté par retriever_adapter.make_retriever) :
    retrieve(question, filters: dict, k: int) -> list[dict]   (déjà triée par pertinence)
    chaque passage = un chunk du Lot 2 (title, section, text, lang, url, source, license,
    region, theme, chunk_id...) + score (RRF), dense_score (cosinus), repli (bool).

Contrat avec le Lot 5 (interface) : rag_answer() renvoie un dict
    {answer, sources, mode, lang, refused, reason, warnings, n_retrieved, n_used, best_relevance}
"""
import re

from .config import get_settings
from .llm import call_llm
from .prompts import (
    MAX_TOKENS_BY_MODE, MODES, NO_INFO_TAG, OUT_OF_SCOPE, REFUSALS, TOP_K_BY_MODE, build_messages,
    build_retry_message,
)
from .utils import detect_lang, detect_mode, format_context, grounding_score, mentions_topic, out_of_scope_term, topic_terms

_CITATION = re.compile(r"\[(\d+)\]")
_LEADING_RUN = re.compile(r"^\s*(?:\[\d+\]\s*)+")
# un numéro suivi d'une fin de ligne, de ponctuation ou de "**" : style « phrase [n] »
_SUFFIX_EVIDENCE = re.compile(r"\[\d+\](?=[ \t]*(?:$|[.,;:!?*)»]))", re.MULTILINE)
_SENTENCE = re.compile(r"[^.!?؟]+[.!?؟]?(?:\s*\[\d+\])*")
_SEGMENT = re.compile(r"((?:\[\d+\]\s*)+)([^\[]*)")


def relevance(p: dict):
    """Pertinence d'un passage sur une échelle COMPARABLE à un seuil (cosinus), sinon None.

    Le score du Lot 3 en mode hybride est un score RRF (~0,03 au maximum) : inutilisable
    comme seuil. On utilise donc dense_score (cosinus). En mode bm25 seul, il n'y a pas de
    cosinus : pas de seuil, c'est alors le LLM qui juge ([NO_INFO]).
    """
    if p.get("dense_score") is not None:
        return p["dense_score"]
    if str(p.get("mode", "")).startswith("bm25"):
        return None
    return p.get("score")  # retrievers simples (mock) dont le score est déjà un cosinus


def best_relevance(passages: list):
    vals = [v for v in (relevance(p) for p in passages) if v is not None]
    return max(vals) if vals else None


def rag_answer(
    question: str,
    retrieve,
    filters=None,
    mode: str = "auto",
    lang=None,
    top_k=None,
    min_score=None,
    retry_citations: bool = True,
    scope_check: bool = True,
) -> dict:
    s = get_settings()
    question = question.strip()
    if not question:
        raise ValueError("La question est vide.")

    lang = lang or detect_lang(question)
    mode = detect_mode(question) if mode == "auto" else mode
    if mode not in MODES:
        raise ValueError(f"Mode inconnu : {mode!r} (choix : auto, {', '.join(MODES)})")
    top_k = top_k or s.top_k or TOP_K_BY_MODE[mode]
    min_score = s.min_score if min_score is None else min_score

    result = {
        "answer": "", "sources": [], "mode": mode, "lang": lang, "refused": False,
        "reason": None, "warnings": [], "n_retrieved": 0, "n_used": 0, "best_relevance": None,
    }

    # 0) Garde-fou n°0 : question sur un autre pays -> hors périmètre, sans même chercher
    if scope_check and out_of_scope_term(question):
        result.update(answer=OUT_OF_SCOPE[lang], refused=True, reason="out_of_scope")
        return result

    # 1) Récupération (Lot 3)
    # Itinéraire : un lieu = une étape. On demande plus de passages au Lot 3, puis on garde un seul
    # passage par page source (sinon le LLM répète « Carthage » à plusieurs étapes).
    fetch_k = top_k * 3 // 2 if mode == "itinerary" else top_k
    passages = list(retrieve(question, filters or {}, fetch_k))
    if mode == "itinerary":
        passages = _dedupe_by_source(passages)
    passages = passages[:top_k]
    best = best_relevance(passages)

    result["n_retrieved"] = len(passages)
    result["best_relevance"] = best

    # 2) Garde-fou n°1 : rien d'assez pertinent -> on n'appelle pas le LLM
    if not passages or (best is not None and best < min_score):
        result.update(answer=REFUSALS[lang], refused=True, reason="no_relevant_passage")
        return result

    # 2 bis) Récit : seuls les passages qui parlent du sujet demandé alimentent l'histoire.
    # Les autres (même proches par le cosinus) servent au LLM à mélanger des lieux et des légendes.
    if mode == "story" and lang != "ar":
        terms = topic_terms(question)
        if terms:
            on_topic = [p for p in passages if mentions_topic(p, terms)]
            if not on_topic:
                result.update(answer=REFUSALS[lang], refused=True, reason="no_topic_passage")
                return result
            if len(on_topic) < len(passages):
                result["warnings"].append("passages_hors_sujet_ecartes")
            passages = on_topic

    # 3) Génération
    context, used = format_context(passages, s.max_chars_per_passage, s.max_context_chars)
    relaxed = any(p.get("repli") for p in used)
    if relaxed:
        result["warnings"].append("filtre_assoupli")
    system, user = build_messages(question, context, mode, lang, relaxed)
    raw = call_llm(system, user, max_tokens=MAX_TOKENS_BY_MODE[mode]).strip()
    result["n_used"] = len(used)

    # 4) Garde-fou n°2 : le LLM juge lui-même le contexte insuffisant
    if raw.startswith(NO_INFO_TAG):
        detail = raw[len(NO_INFO_TAG):].strip(" :-\n")
        answer = REFUSALS[lang] + (f" {detail}" if detail else "")
        result.update(answer=answer, refused=True, reason="llm_no_info")
        result["sources"] = _sources(used, cited=set())
        return result

    # 5) Vérification des citations : on retire les numéros inventés
    valid = set(range(1, len(used) + 1))
    answer, cited, had_invalid = _check_citations(raw, valid)

    # 5 bis) Citations absentes ou trop rares : une seule relance (les petits LLM oublient les [n],
    # ou n'en mettent qu'un seul pour tout un paragraphe, ce qui attribuerait tout à la même source)
    coverage = citation_coverage(answer) if cited else 0.0
    if coverage < MIN_COVERAGE and retry_citations:
        raw2 = call_llm(system, build_retry_message(user, raw),
                        max_tokens=MAX_TOKENS_BY_MODE[mode]).strip()
        if not raw2.startswith(NO_INFO_TAG):
            answer2, cited2, invalid2 = _check_citations(raw2, valid)
            cov2 = citation_coverage(answer2) if cited2 else 0.0
            if cov2 > coverage:
                raw, answer, cited, had_invalid, coverage = raw2, answer2, cited2, invalid2, cov2
                result["warnings"].append("citation_retry")
    if not cited:
        result["warnings"].append("no_citation")
    elif coverage < MIN_COVERAGE:
        result["warnings"].append("low_citation_coverage")
    if had_invalid:
        result["warnings"].append("invalid_citation_removed")
    # Ancrage lexical : alerte uniquement (jamais un refus). Deux diagnostics distincts :
    #  - weak_grounding   : les mots distinctifs de la réponse n'apparaissent dans AUCUN passage
    #                       fourni -> le LLM a probablement répondu de mémoire ;
    #  - citation_mismatch: ils apparaissent dans le contexte mais pas dans les passages cités
    #                       -> la bonne information est là, mais la citation pointe ailleurs.
    g_cited = grounding_score(answer, question, [used[i - 1] for i in sorted(cited)], lang)
    g_context = grounding_score(answer, question, used, lang)
    result["grounding"] = None if g_cited is None else round(g_cited, 2)
    result["grounding_context"] = None if g_context is None else round(g_context, 2)
    if g_context is not None and g_context < 0.35:
        result["warnings"].append("weak_grounding")
    elif g_cited is not None and g_cited < 0.35:
        result["warnings"].append("citation_mismatch")
    result["raw_answer"] = raw
    result["citation_coverage"] = round(coverage, 2)
    result.update(answer=answer, sources=_sources(used, cited))
    return result


MIN_COVERAGE = 0.6  # part minimale de phrases couvertes par une citation
_BLOCK_SPLIT = re.compile(r"\n\s*\n|\n(?=\s*\d+[.)]\s)")
_ENUMERATOR = re.compile(r"^\s*\d+[.)]\s+")


def citation_coverage(answer: str) -> float:
    """Part des phrases couvertes par une citation, de 0 à 1.

    On raisonne par bloc (paragraphe ou étape numérotée) : dans un bloc, chaque phrase qui porte
    un numéro en couvre elle-même plus une voisine (une étape « lieu [n]. détail. » est couverte),
    mais un seul numéro ne couvre pas tout un long paragraphe.
    """
    covered = total = 0
    for block in _BLOCK_SPLIT.split(answer):
        sentences = [s for s in _SENTENCE.findall(_ENUMERATOR.sub("", block)) if any(c.isalpha() for c in s)]
        if not sentences:
            continue
        cited = sum(bool(_CITATION.search(s)) for s in sentences)
        covered += min(len(sentences), 2 * cited)
        total += len(sentences)
    return covered / total if total else 0.0


def _prefix_to_suffix(text: str) -> str:
    """Convertit « [1] Phrase. [2] Phrase. » en « Phrase. [1] Phrase. [2] ».

    Les petits LLM recopient le format du contexte et placent le numéro AVANT la phrase.
    On déplace chaque numéro à la fin de la phrase qui le suit ; les numéros déjà placés
    en fin de phrase sont conservés (sans doublon).
    """
    out = []  # liste de [texte, [numéros]]
    for m in _SEGMENT.finditer(text):
        nums = re.findall(r"\d+", m.group(1))
        body = m.group(2).strip()
        if body or not out:
            out.append([body, nums])
        else:  # numéros sans texte derrière : ils appartiennent à la phrase précédente
            out[-1][1].extend(nums)
    parts = []
    for body, nums in out:
        uniq = list(dict.fromkeys(nums))
        parts.append((body + " " + "".join(f"[{n}]" for n in uniq)).strip())
    return " ".join(parts)


def _normalize_leading_markers(answer: str) -> str:
    """Traite les numéros collés au tout début de la réponse (habitude des petits LLM).

    - Si le reste de la réponse cite en fin de phrase / d'étape (« … [2] », « **Étape 2 [3]** »),
      le début n'est qu'un résidu recopié du contexte : on le retire, et on NE TOUCHE PAS aux
      autres citations (elles sont déjà bien placées).
    - Sinon, c'est le style « [1] Phrase. [2] Phrase. » : on déplace chaque numéro à la fin
      de sa phrase.
    """
    m = _LEADING_RUN.match(answer)
    if not m or not answer[m.end():].strip():
        return answer
    rest = answer[m.end():]
    if _SUFFIX_EVIDENCE.search(rest):
        return rest.lstrip()
    return _prefix_to_suffix(answer)


def _check_citations(raw: str, valid: set):
    """Normalise puis vérifie les citations.

    Retourne (réponse nettoyée, numéros cités valides, True si des numéros inventés ont été retirés).
    """
    had_invalid = any(int(n) not in valid for n in _CITATION.findall(raw))
    answer = raw.replace(NO_INFO_TAG, "").strip()
    answer = _normalize_leading_markers(answer)
    answer = _CITATION.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer).strip()
    return answer, {int(n) for n in _CITATION.findall(answer)}, had_invalid


def _dedupe_by_source(passages: list) -> list:
    seen, out = set(), []
    for p in passages:
        key = p.get("url") or p.get("chunk_id") or id(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _sources(used: list, cited: set) -> list:
    return [
        {
            "id": i,
            "title": p.get("title"),
            "section": p.get("section"),
            "source": p.get("source"),
            "url": p.get("url"),
            "license": p.get("license"),
            "redistributable": p.get("redistributable"),
            "region": p.get("region"),
            "theme": p.get("theme"),
            "lang": p.get("lang"),
            "chunk_id": p.get("chunk_id"),
            "relevance": relevance(p),
            "text": p["text"],
            "cited": i in cited,
        }
        for i, p in enumerate(used, 1)
    ]
