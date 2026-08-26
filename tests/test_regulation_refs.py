from ingest.regulation_refs import extract_refs


def test_instrument_with_annex_and_year():
    refs = extract_refs("MARPOL Annex VI covers air pollution; the 1997 Protocol added it.")
    assert refs == [{"instrument": "MARPOL", "detail": "Annex VI", "year": 1997, "raw": "MARPOL"}]


def test_cfr_citation():
    refs = extract_refs("work vests are considered per 46 CFR 26.30-5 to be safety apparel.")
    assert refs == [
        {"instrument": "CFR", "detail": "46 CFR 26.30-5", "year": None, "raw": "46 CFR 26.30-5"}
    ]


def test_no_false_positive_on_unrelated_text():
    assert extract_refs("The vessel departed the harbor at 0600 in heavy seas.") == []
    assert (
        extract_refs("A bill of lading is issued by a carrier acknowledging cargo receipt.") == []
    )


def test_multiple_distinct_instruments():
    text = "Port state control under the Paris MoU checks SOLAS, MARPOL, STCW, and MLC compliance."
    refs = extract_refs(text)
    instruments = {r["instrument"] for r in refs}
    assert instruments == {"SOLAS", "MARPOL", "STCW", "MLC"}


def test_chapter_reference():
    refs = extract_refs("SOLAS Chapter II-1 sets subdivision and stability requirements.")
    assert refs[0]["instrument"] == "SOLAS"
    assert refs[0]["detail"] == "Chapter II-1"


def test_regulation_reference():
    refs = extract_refs("STCW Regulation I/1 sets certification requirements for seafarers.")
    assert refs[0]["instrument"] == "STCW"
    assert refs[0]["detail"] == "Regulation I/1"


def test_deduplicates_identical_references():
    text = "MARPOL Annex VI governs emissions. MARPOL Annex VI also covers SOx limits."
    refs = extract_refs(text)
    # same (instrument, detail, year) triple should not be listed twice
    keys = {(r["instrument"], r["detail"], r["year"]) for r in refs}
    assert len(refs) == len(keys)


def test_empty_text_returns_empty_list():
    assert extract_refs("") == []


def test_case_insensitive_instrument_match_normalizes_to_upper():
    refs = extract_refs("marpol regulations apply to all cargo ships.")
    assert refs[0]["instrument"] == "MARPOL"
