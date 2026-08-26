from rag.cite_check import check_citations

PASSAGES = [
    {
        "content": "The vessel's main engine caught fire after an electrical "
        "short circuit in the generator room, according to the "
        "casualty investigation report.",
        "title": "Engine Room Fire Investigation",
        "url": "https://example.com/engine-fire",
    },
    {
        "content": "Investigators found no evidence of prior mechanical "
        "defects and concluded routine maintenance had been "
        "performed on schedule.",
        "title": "Maintenance Record Review",
        "url": "https://example.com/maintenance",
    },
    {
        "content": "The bill of lading must be signed by the master before "
        "departure and serves as a critical shipping document "
        "for the cargo owner.",
        "title": "Bill of Lading Requirements",
        "url": "https://example.com/bill-of-lading",
    },
]


def test_out_of_range_citation_flagged():
    answer = (
        "The fire started in the generator room due to an electrical short "
        "circuit [1]. Investigators found no prior mechanical defects [5]."
    )
    result = check_citations(answer, PASSAGES)
    assert result["valid"] is False
    assert result["out_of_range"] == [5]


def test_in_range_citations_not_flagged_as_out_of_range():
    answer = (
        "The vessel's main engine caught fire after an electrical short "
        "circuit in the generator room [1]. Investigators found no evidence "
        "of prior mechanical defects and maintenance had been performed on "
        "schedule [2]. The bill of lading must be signed by the master "
        "before departure [3]."
    )
    result = check_citations(answer, PASSAGES)
    assert result["out_of_range"] == []
    assert result["valid"] is True
    assert result["citation_count"] == 3


def test_weak_grounding_flagged_for_mismatched_content():
    # Cites the bill-of-lading passage [3] for a claim about an engine fire --
    # topically unrelated, so word overlap should be near zero.
    answer = "The engine caught fire during the voyage [3]."
    result = check_citations(answer, PASSAGES)
    assert result["valid"] is False
    assert len(result["weak_grounding"]) == 1
    flagged = result["weak_grounding"][0]
    assert flagged["citation_index"] == 3
    assert flagged["overlap_ratio"] < 0.08


def test_close_paraphrase_not_flagged_as_weak_grounding():
    # Same claim as passage [1], paraphrased -- should NOT be flagged.
    answer = "The ship's main engine caught fire due to an electrical short circuit in the generator room [1]."
    result = check_citations(answer, PASSAGES)
    assert result["weak_grounding"] == []
    assert result["valid"] is True


def test_citation_marker_after_period_stays_attached_to_its_sentence():
    # "[1]" landing after the full stop must still be matched against the
    # sentence it's citing, not treated as its own detached fragment.
    answer = "The vessel's main engine caught fire after an electrical short circuit in the generator room. [1]"
    result = check_citations(answer, PASSAGES)
    assert result["citation_count"] == 1
    assert result["weak_grounding"] == []
    assert result["valid"] is True


def test_no_citations_is_valid_with_zero_count():
    result = check_citations("No documents ingested yet.", PASSAGES)
    assert result["valid"] is True
    assert result["citation_count"] == 0
    assert result["out_of_range"] == []
    assert result["weak_grounding"] == []


def test_empty_answer_handles_gracefully():
    result = check_citations("", PASSAGES)
    assert result["valid"] is True
    assert result["citation_count"] == 0


def test_multiple_citations_in_one_sentence():
    answer = (
        "The vessel's main engine caught fire after an electrical short "
        "circuit in the generator room, and investigators found no prior "
        "mechanical defects [1][2]."
    )
    result = check_citations(answer, PASSAGES)
    assert result["citation_count"] == 2
    assert result["out_of_range"] == []
