"""Tests du Lot 4 sans LLM ni modèle (LLM simulé). Depuis la racine :
    python -m unittest discover generation/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generation import pipeline  # noqa: E402
from generation.mock_retriever import retrieve  # noqa: E402
from generation.utils import detect_lang, detect_mode, format_context  # noqa: E402

REAL = lambda q, f, k: [  # noqa: E731  (passage au format réel du Lot 3, score RRF + cosinus)
    {"chunk_id": "c1", "title": "Amphithéâtre d'El Jem", "section": "Histoire", "lang": "fr",
     "text": "Le grand amphithéâtre romain d'El Jem.", "url": "http://x", "license": "CC BY-SA 4.0",
     "region": "Mahdia", "theme": "patrimoine_archeologique", "score": 0.0328,
     "dense_score": DENSE, "mode": "hybrid", "repli": REPLI},
]
DENSE, REPLI = 0.85, False


class Base(unittest.TestCase):
    def setUp(self):
        self._orig = pipeline.call_llm

    def tearDown(self):
        pipeline.call_llm = self._orig


class TestUtils(Base):
    def test_lang(self):
        self.assertEqual(detect_lang("Que peut-on visiter à Kairouan ?"), "fr")
        self.assertEqual(detect_lang("What can I visit in Tunis?"), "en")
        self.assertEqual(detect_lang("ما هي أشهر المعالم في القيروان؟"), "ar")

    def test_mode(self):
        self.assertEqual(detect_mode("Propose-moi un itinéraire de 3 jours"), "itinerary")
        self.assertEqual(detect_mode("Raconte-moi la légende de Carthage"), "story")
        self.assertEqual(detect_mode("Où est Dougga ?"), "answer")

    def test_context_has_title_region_lang(self):
        ctx, used = format_context(REAL("q", {}, 1), 2000, 12000)
        self.assertIn("[1] Amphithéâtre d'El Jem — Histoire (Mahdia, fr)", ctx)
        self.assertEqual(len(used), 1)


class TestPipeline(Base):
    def test_refusal_without_llm_call(self):
        def boom(*a, **k):
            raise AssertionError("Le LLM ne doit pas être appelé")
        pipeline.call_llm = boom
        r = pipeline.rag_answer("Quel est le prix d'un billet d'avion Paris-Tokyo ?", retrieve, min_score=0.3)
        self.assertTrue(r["refused"])
        self.assertEqual(r["reason"], "no_relevant_passage")

    def test_threshold_uses_cosine_not_rrf(self):
        """Régression : le score RRF (0,03) ne doit JAMAIS être comparé au seuil."""
        global DENSE
        pipeline.call_llm = lambda s, u, **k: "Un amphithéâtre romain [1]."
        DENSE = 0.85
        r = pipeline.rag_answer("Où voir un amphithéâtre romain ?", REAL, min_score=0.75)
        self.assertFalse(r["refused"])
        DENSE = 0.60
        r = pipeline.rag_answer("Où voir un amphithéâtre romain ?", REAL, min_score=0.75)
        self.assertTrue(r["refused"])
        DENSE = 0.85

    def test_bm25_mode_has_no_threshold(self):
        pipeline.call_llm = lambda s, u, **k: "ok [1]"
        bm = lambda q, f, k: [{"title": "T", "text": "x", "score": 7.2, "bm25_score": 7.2, "mode": "bm25"}]  # noqa: E731
        r = pipeline.rag_answer("question", bm, min_score=0.75)
        self.assertFalse(r["refused"])

    def test_citations_invalid_removed(self):
        pipeline.call_llm = lambda s, u, **k: "Kairouan a une grande mosquée fondée en 670 [1][9]."
        r = pipeline.rag_answer("Que peut-on visiter à Kairouan ?", retrieve, min_score=0.3)
        self.assertNotIn("[9]", r["answer"])
        self.assertIn("invalid_citation_removed", r["warnings"])
        self.assertEqual([s["id"] for s in r["sources"] if s["cited"]], [1])

    def test_llm_no_info(self):
        pipeline.call_llm = lambda s, u, **k: "[NO_INFO] Le contexte ne parle pas de cela."
        r = pipeline.rag_answer("Parle-moi de Kairouan", retrieve, min_score=0.3)
        self.assertTrue(r["refused"])
        self.assertEqual(r["reason"], "llm_no_info")

    def test_relaxed_filter_noted(self):
        global REPLI
        seen = {}
        def fake(s, u, **k):
            seen["user"] = u
            return "ok [1]"
        pipeline.call_llm = fake
        REPLI = True
        r = pipeline.rag_answer("Où voir un amphithéâtre romain ?", REAL, min_score=0.75)
        REPLI = False
        self.assertIn("filtre_assoupli", r["warnings"])
        self.assertIn("NOTE", seen["user"])

    def test_top_k_by_mode_and_max_tokens(self):
        got = {}
        def fake_retrieve(q, f, k):
            got["k"] = k
            return REAL(q, f, k)
        def fake_llm(s, u, **kw):
            got["max_tokens"] = kw["max_tokens"]
            return "ok [1]"
        pipeline.call_llm = fake_llm
        pipeline.rag_answer("Propose un itinéraire", fake_retrieve, min_score=0.5)
        self.assertEqual(got, {"k": 12, "max_tokens": 1000})  # itinéraire : 12 demandés, dédoublonnés puis coupés à 8

    def test_citation_retry_succeeds(self):
        calls = []
        def fake(s, u, **k):
            calls.append(u)
            return "Les makrouds sont réputés." if len(calls) == 1 else "Les makrouds sont réputés [1]."
        pipeline.call_llm = fake
        r = pipeline.rag_answer("Que goûter à Kairouan ?", REAL, min_score=0.5)
        self.assertEqual(len(calls), 2)
        self.assertIn("TA RÉPONSE PRÉCÉDENTE", calls[1])
        self.assertIn("citation_retry", r["warnings"])
        self.assertNotIn("no_citation", r["warnings"])
        self.assertEqual([s["id"] for s in r["sources"] if s["cited"]], [1])

    def test_citation_retry_fails_keeps_warning(self):
        n = []
        pipeline.call_llm = lambda s, u, **k: (n.append(1), "Sans citation.")[1]
        r = pipeline.rag_answer("Que goûter à Kairouan ?", REAL, min_score=0.5)
        self.assertEqual(len(n), 2)
        self.assertIn("no_citation", r["warnings"])

    def test_no_retry_when_disabled(self):
        n = []
        pipeline.call_llm = lambda s, u, **k: (n.append(1), "Sans citation.")[1]
        pipeline.rag_answer("Que goûter à Kairouan ?", REAL, min_score=0.5, retry_citations=False)
        self.assertEqual(len(n), 1)

    def test_reminder_at_end_of_prompt(self):
        seen = {}
        def fake(s, u, **k):
            seen["u"] = u
            return "ok [1]"
        pipeline.call_llm = fake
        pipeline.rag_answer("Où est El Jem ?", REAL, min_score=0.5)
        self.assertTrue(seen["u"].rstrip().split("\n")[-1].startswith("RAPPEL"))

    def test_prefix_style_converted(self):
        """Le LLM met le numéro AVANT la phrase : on le déplace à la fin de sa phrase."""
        pipeline.call_llm = lambda s, u, **k: "[1] Premier plat. [1] Deuxième plat. [1] Un marché."
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertEqual(r["answer"], "Premier plat. [1] Deuxième plat. [1] Un marché. [1]")
        self.assertNotIn("invalid_citation_removed", r["warnings"])

    def test_prefix_style_keeps_alignment(self):
        sources = lambda q, f, k: [dict(REAL(q, f, 1)[0], chunk_id=f"c{i}") for i in range(3)]  # noqa: E731
        pipeline.call_llm = lambda s, u, **k: "[1] Plat A. [2] Plat B. [3] Marché C."
        r = pipeline.rag_answer("Que goûter à Sfax ?", sources, min_score=0.5)
        self.assertEqual(r["answer"], "Plat A. [1] Plat B. [2] Marché C. [3]")
        self.assertEqual([s["id"] for s in r["sources"] if s["cited"]], [1, 2, 3])

    def test_mixed_prefix_and_suffix_deduplicated(self):
        pipeline.call_llm = lambda s, u, **k: "[1] Le souk est une bonne option. [1]"
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertEqual(r["answer"], "Le souk est une bonne option. [1]")

    def test_suffix_style_untouched(self):
        pipeline.call_llm = lambda s, u, **k: "Phrase A [1]. Phrase B [1]."
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertEqual(r["answer"], "Phrase A [1]. Phrase B [1].")

    def test_invalid_number_flagged_and_raw_kept(self):
        pipeline.call_llm = lambda s, u, **k: "Phrase A [1][9]."
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertIn("invalid_citation_removed", r["warnings"])
        self.assertEqual(r["raw_answer"], "Phrase A [1][9].")
        self.assertNotIn("[9]", r["answer"])

    def test_single_marker_for_whole_paragraph_is_weak(self):
        """Régression (cas réel) : un seul [1] pour 4 phrases ne doit pas passer pour une citation fiable."""
        calls = []
        def fake(s, u, **k):
            calls.append(u)
            if len(calls) == 1:
                return "[1] Phrase A. Phrase B. Phrase C. Phrase D."
            return "Phrase A [1]. Phrase B [1]. Phrase C [1]. Phrase D [1]."
        pipeline.call_llm = fake
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertEqual(len(calls), 2)
        self.assertIn("citation_retry", r["warnings"])
        self.assertNotIn("low_citation_coverage", r["warnings"])
        self.assertEqual(r["citation_coverage"], 1.0)

    def test_low_coverage_warning_if_retry_does_not_help(self):
        pipeline.call_llm = lambda s, u, **k: "[1] Phrase A. Phrase B. Phrase C. Phrase D."
        r = pipeline.rag_answer("Que goûter à Sfax ?", REAL, min_score=0.5)
        self.assertIn("low_citation_coverage", r["warnings"])
        self.assertLess(r["citation_coverage"], 0.6)

    def test_coverage_function(self):
        from generation.pipeline import citation_coverage
        self.assertEqual(citation_coverage("A. [1] B. [2] C. [3]"), 1.0)
        self.assertEqual(citation_coverage("A [1]. B. C. D. E."), 0.4)
        self.assertEqual(citation_coverage("A. B. C. D. [1]"), 0.5)
        self.assertEqual(citation_coverage("Une seule phrase [1]."), 1.0)

    def test_coverage_numbered_steps_not_penalised(self):
        """Régression (cas réel) : « 1. » n'est pas une phrase ; une étape « lieu [n]. détail. » est couverte."""
        from generation.pipeline import citation_coverage
        text = ("Voici un itinéraire :\n\n1. Partez de Tunis pour visiter Carthage [1]. Découvrez les thermes.\n\n"
                "2. Allez à Dougga [4]. Explorez le théâtre.\n\n3. Visitez Kerkouane [5]. Découvrez la cité.\n\n"
                "Ce parcours couvre plusieurs régions.")
        self.assertGreaterEqual(citation_coverage(text), 0.6)

    def test_coverage_one_marker_for_long_paragraph_is_low(self):
        from generation.pipeline import citation_coverage
        para = "S1. S2. S3. S4. S5. S6. [1]"
        self.assertLess(citation_coverage(para), 0.6)

    def test_real_itinerary_case_citations_untouched(self):
        """Régression (cas réel) : résidu '[1] [1] [2]…' au début + citations déjà bien placées
        dans les titres d'étapes : seules les citations bien placées doivent rester, à leur place."""
        sources = lambda q, f, k: [dict(REAL(q, f, 1)[0], chunk_id=f"c{i}", url=f"http://x/{i}") for i in range(3)]  # noqa: E731
        raw = ("[1] [1] [2] [3] Voici l'itinéraire :\n\n**Étape 1 : Carthage [1]**\n- Les thermes.\n\n"
               "**Étape 2 : Bardo [3]**\n- Le musée.\n\n**Étape 3 : Dougga [2]**\n- Le théâtre.")
        pipeline.call_llm = lambda s, u, **k: raw
        r = pipeline.rag_answer("Propose un itinéraire", sources, min_score=0.5)
        self.assertTrue(r["answer"].startswith("Voici l'itinéraire"))
        self.assertIn("**Étape 1 : Carthage [1]**", r["answer"])
        self.assertIn("**Étape 2 : Bardo [3]**", r["answer"])
        self.assertIn("**Étape 3 : Dougga [2]**", r["answer"])
        for w in ("no_citation", "low_citation_coverage", "invalid_citation_removed", "citation_retry"):
            self.assertNotIn(w, r["warnings"])

    def test_itinerary_keeps_one_passage_per_source(self):
        def many(q, f, k):
            base = REAL(q, f, 1)[0]
            urls = ["u1", "u1", "u2", "u1", "u3"]
            return [dict(base, chunk_id=f"c{i}", url=u) for i, u in enumerate(urls)]
        seen = {}
        def fake(s, u, **k):
            seen["u"] = u
            return "ok [1]"
        pipeline.call_llm = fake
        r = pipeline.rag_answer("Propose un itinéraire", many, min_score=0.5)
        self.assertEqual([s["url"] for s in r["sources"]], ["u1", "u2", "u3"])

    def test_filters_forwarded(self):
        got = {}
        def fake_retrieve(q, f, k):
            got.update(f)
            return REAL(q, f, k)
        pipeline.call_llm = lambda s, u, **k: "ok [1]"
        pipeline.rag_answer("Que goûter à Sfax ?", fake_retrieve, filters={"region": "Sfax"}, min_score=0.5)
        self.assertEqual(got, {"region": "Sfax"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
