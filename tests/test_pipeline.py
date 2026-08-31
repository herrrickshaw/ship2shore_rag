from rag.pipeline import CHECKLIST_SYSTEM_PROMPT, SYSTEM_PROMPT, _system_prompt


def test_system_prompt_defaults_to_prose():
    assert _system_prompt(checklist=False) == SYSTEM_PROMPT


def test_system_prompt_checklist_mode():
    assert _system_prompt(checklist=True) == CHECKLIST_SYSTEM_PROMPT


def test_checklist_prompt_asks_for_numbered_steps():
    assert "numbered checklist" in CHECKLIST_SYSTEM_PROMPT
    assert "[1]" in CHECKLIST_SYSTEM_PROMPT


def test_ask_returns_no_documents_message_without_hitting_generation(monkeypatch):
    import rag.pipeline as pipeline

    monkeypatch.setattr(pipeline, "retrieve", lambda *a, **k: [])
    result = pipeline.ask("what causes hull fatigue?", checklist=True)
    assert result["passages"] == []
    assert "ingest" in result["answer"]
