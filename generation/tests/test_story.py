"""Mode récit : seuls les passages qui parlent du sujet demandé sont utilisés."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generation import pipeline  # noqa: E402
from generation.prompts import build_messages  # noqa: E402
from generation.utils import mentions_topic, topic_terms  # noqa: E402


def p(title, text, url):
    return {"chunk_id": url, "title": title, "text": text, "url": url, "lang": "fr",
            "dense_score": 0.9, "score": 0.03, "mode": "hybrid"}


CARTHAGE = p("Site archéologique de Carthage", "Fondée par Elyssa-Didon selon la légende.", "u1")
CHARMOULA = p("Qui a inventé la charmoula ?", "Un mets festif de la cuisine tunisienne.", "u2")
DJERBA = p("Djerba — Croyances", "Sidi Satouri a transformé un lieu en mosquée.", "u3")


class TestStory(unittest.TestCase):
    def setUp(self):
        self._orig = pipeline.call_llm
        self.seen = {}
        def fake(s, u, **k):
            self.seen["u"] = u
            return "Récit. [1]"
        pipeline.call_llm = fake

    def tearDown(self):
        pipeline.call_llm = self._orig

    def test_terms(self):
        self.assertEqual(topic_terms("Raconte-moi la légende de Carthage"), ["carthage"])
        self.assertEqual(topic_terms("Raconte-moi une légende"), [])

    def test_prefix_match(self):
        self.assertTrue(mentions_topic({"title": "", "text": "les Carthaginois"}, ["carthage"]))
        self.assertFalse(mentions_topic({"title": "Djerba", "text": "une île"}, ["carthage"]))

    def test_off_topic_passages_dropped(self):
        r = pipeline.rag_answer("Raconte-moi la légende de Carthage",
                                lambda q, f, k: [CARTHAGE, CHARMOULA, DJERBA], min_score=0.5)
        self.assertEqual([s["url"] for s in r["sources"]], ["u1"])
        self.assertIn("passages_hors_sujet_ecartes", r["warnings"])
        self.assertNotIn("charmoula", self.seen["u"])

    def test_refuses_when_no_passage_mentions_subject(self):
        pipeline.call_llm = lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM appelé"))
        r = pipeline.rag_answer("Raconte-moi la légende de Carthage",
                                lambda q, f, k: [CHARMOULA, DJERBA], min_score=0.5)
        self.assertTrue(r["refused"])
        self.assertEqual(r["reason"], "no_topic_passage")

    def test_other_modes_not_filtered(self):
        r = pipeline.rag_answer("Que savoir sur Carthage ?", lambda q, f, k: [CARTHAGE, CHARMOULA], min_score=0.5)
        self.assertEqual(len(r["sources"]), 2)

    def test_no_terms_no_filter(self):
        r = pipeline.rag_answer("Raconte-moi une légende", lambda q, f, k: [CARTHAGE, CHARMOULA], min_score=0.5)
        self.assertEqual(len(r["sources"]), 2)

    def test_itinerary_prompt_asks_for_physical_places(self):
        system, _ = build_messages("q", "[1] x", "itinerary", "fr")
        self.assertIn("lieux physiques", system)


if __name__ == "__main__":
    unittest.main()
