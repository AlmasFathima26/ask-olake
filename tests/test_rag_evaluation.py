import json
from pathlib import Path

import rag

ROOT = Path(__file__).resolve().parents[1]


def test_retrieval_evaluation_cases_match_expected_evidence():
    cases = json.loads(
        (Path(__file__).parent / "rag_eval_cases.json").read_text(encoding="utf-8")
    )
    assert len(cases) >= 20
    corpus = " ".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend" / "corpus").glob("*.md")
    )
    corpus = " ".join(corpus.lower().split())

    for case in cases:
        if "expected_sources" in case:
            results = rag.retrieve(case["question"])
            _, citations, _, low_confidence = rag.context_and_sources(results)
            assert not low_confidence, case["question"]
            for expected in case["expected_sources"]:
                assert expected["source"] in corpus
                evidence = [
                    result["chunk"]
                    for result in results
                    if result["chunk"]["source"] == expected["source"]
                    and result["chunk"]["title"] == expected["title"]
                ]
                assert evidence, (
                    case["question"],
                    expected,
                    [(result["score"], result["chunk"]["title"]) for result in results],
                )
                assert any(
                    citation["url"] == expected["source"]
                    and expected["title"] in citation["title"]
                    for citation in citations
                ), (case["question"], expected, citations)
                evidence_text = " ".join(
                    " ".join(chunk["text"].lower().split()) for chunk in evidence
                )
                for term in expected["required_terms"]:
                    assert " ".join(term.lower().split()) in evidence_text, (
                        case["question"],
                        expected["source"],
                        term,
                    )
            continue
        if case["expected_source"] is None:
            results = rag.retrieve(case["question"])
            assert max((result["score"] for result in results), default=0.0) < rag.SIM_THRESHOLD, (
                case["question"],
                [(result["score"], result["chunk"]["title"]) for result in results],
            )
            continue
        assert case["expected_source"] in corpus
        for term in case["required_terms"]:
            assert " ".join(term.lower().split()) in corpus
        results = rag.retrieve(case["question"])
        evidence = [
            result["chunk"]
            for result in results
            if result["chunk"]["source"] == case["expected_source"]
            and result["chunk"]["title"] == case["expected_title"]
        ]
        assert evidence, (
            case["question"],
            [(result["score"], result["chunk"]["title"]) for result in results],
        )
        _, citations, _, low_confidence = rag.context_and_sources(results)
        assert not low_confidence, case["question"]
        assert any(
        citation["url"] == case["expected_source"]
            and case["expected_title"] in citation["title"]
        for citation in citations
        ), (case["question"], citations)
        retrieved_text = " ".join(
            " ".join(chunk["text"].lower().split()) for chunk in evidence
        )
        for term in case["required_terms"]:
            assert " ".join(term.lower().split()) in retrieved_text, (
                case["question"],
                term,
            )
