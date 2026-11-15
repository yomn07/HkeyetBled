"""Tests du garde-fou de périmètre et de l'ancrage lexical (sans LLM ni modèle)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generation import pipeline  # noqa: E402
from generation.prompts import build_messages  # noqa: E402
from generation.utils import grounding_score, out_of_scope_term  # noqa: E402


def passage(text, lang="fr"):
    return {"chunk_id": "c", "title": "T", "text": text, "lang": lang, "dense_score": 0.9,
            "score": 0.03, "mode": "hybrid"}


class TestScope(unittest.TestCase):
    def test_foreign_questions_blocked(self):
        for q in ["Quelle est la capitale de l'Algérie ?", "Quel est le climat au Maroc en été ?",
                  "What is the capital of Algeria?", "ما هي عاصمة الجزائر؟", "Plats typiques de France ?"]:
            self.assertIsNotNone(out_of_scope_term(q), q)

    def test_tunisian_or_neutral_questions_pass(self):
        for q in ["Que visiter à Sfax ?", "Comment aller en Tunisie depuis la France ?",
                  "Quelle est la distance entre Sfax et Alger ?", "Où trouver une machine à café ?",
                  "Que goûter à Djerba ?", "ما هي المدينة البونيقية المكتشفة في الوطن القبلي؟"]:
            self.assertIsNone(out_of_scope_term(q), q)

    def test_pipeline_refuses_before_retrieval_and_llm(self):
        def boom(*a, **k):
            raise AssertionError("ne doit pas être appelé")
        orig = pipeline.call_llm
        pipeline.call_llm = boom
        try:
            r = pipeline.rag_answer("Quelle est la capitale de l'Algérie ?", boom)
        finally:
            pipeline.call_llm = orig
        self.assertTrue(r["refused"])
        self.assertEqual(r["reason"], "out_of_scope")
        self.assertIn("périmètre", r["answer"])

    def test_scope_check_can_be_disabled(self):
        orig = pipeline.call_llm
        pipeline.call_llm = lambda s, u, **k: "ok [1]"
        try:
            r = pipeline.rag_answer("Capitale de l'Algérie ?", lambda q, f, k: [passage("Texte.")], scope_check=False)
        finally:
            pipeline.call_llm = orig
        self.assertNotEqual(r["reason"], "out_of_scope")


class TestGrounding(unittest.TestCase):
    def test_ungrounded_answer_scores_low(self):
        s = grounding_score("La capitale est Alger. [2]", "Quelle est la capitale de l'Algérie ?",
                            [passage("Habib Bourguiba a mené des réformes en Tunisie.")], "fr")
        self.assertEqual(s, 0.0)

    def test_grounded_answer_scores_high(self):
        s = grounding_score("Le grand amphithéâtre romain d'El Jem. [1]", "Où voir un amphithéâtre ?",
                            [passage("Le grand amphithéâtre romain d'El Jem est un site majeur.")], "fr")
        self.assertGreaterEqual(s, 0.5)

    def test_not_computed_for_arabic_or_other_language(self):
        self.assertIsNone(grounding_score("كركوان", "q", [passage("x", "ar")], "ar"))
        self.assertIsNone(grounding_score("Ancient ruins", "q", [passage("ruines", "fr")], "en"))

    def test_pipeline_warns_on_weak_grounding(self):
        orig = pipeline.call_llm
        pipeline.call_llm = lambda s, u, **k: "Le colisée de Thysdrus se trouve à Kairouan. [1]"
        try:
            r = pipeline.rag_answer("Où voir un amphithéâtre romain ?",
                                    lambda q, f, k: [passage("Le grand amphithéâtre romain d'El Jem.")], min_score=0.5)
        finally:
            pipeline.call_llm = orig
        self.assertIn("weak_grounding", r["warnings"])


class TestNumbersAndDiagnosis(unittest.TestCase):
    def test_numbers_are_checked(self):
        ok = grounding_score("Elle date de 146 avant notre ère. [1]", "Quand ?", [passage("Détruite en 146 av. J.-C.")], "fr")
        ko = grounding_score("Elle date de 999 avant notre ère. [1]", "Quand ?", [passage("Détruite en 146 av. J.-C.")], "fr")
        self.assertGreater(ok, ko)

    def test_number_formats_match(self):
        s = grounding_score("Capacité de 35,000 places. [1]", "q", [passage("Capacité : 35 000 places.")], "fr")
        self.assertEqual(s, 1.0)

    def test_citation_mismatch_vs_weak_grounding(self):
        orig = pipeline.call_llm
        ps = lambda q, f, k: [passage("Le grand amphithéâtre romain."), passage("Capacité estimée : 35 000 spectateurs.")]  # noqa: E731
        try:
            pipeline.call_llm = lambda s, u, **k: "Le colisée accueille 35 000 spectateurs. [1]"
            r = pipeline.rag_answer("Quelle est la capacité du colisée ?", ps, min_score=0.5)
            self.assertIn("citation_mismatch", r["warnings"])
            self.assertNotIn("weak_grounding", r["warnings"])
            pipeline.call_llm = lambda s, u, **k: "Le colisée accueille 99 000 gladiateurs. [1]"
            r = pipeline.rag_answer("Quelle est la capacité du colisée ?", ps, min_score=0.5)
            self.assertIn("weak_grounding", r["warnings"])
        finally:
            pipeline.call_llm = orig


class TestPrompt(unittest.TestCase):
    def test_story_mode_is_strict(self):
        system, _ = build_messages("q", "[1] x", "story", "fr")
        self.assertIn("ne mélange pas", system)
        self.assertIn("[NO_INFO]", system.split("FORMAT")[1])

    def test_refusal_example_and_rule(self):
        system, _ = build_messages("q", "[1] x", "answer", "fr")
        self.assertIn("EXEMPLE DE REFUS", system)
        self.assertIn("JAMAIS avec tes propres connaissances", system)
        self.assertIn("[NO_INFO]", system)


if __name__ == "__main__":
    unittest.main()
