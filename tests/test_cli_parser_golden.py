"""Characterisation: the top-level cli.py argparse tree is pinned to a golden
file captured before main() was split into per-command builders."""

import argparse
import json
from pathlib import Path

import cli
from tests.test_ops_cli_parser_golden import _describe

GOLDEN = Path(__file__).with_name("golden_cli_parser.json")


class _Captured(Exception):
    pass


def _capture_parser(monkeypatch):
    def grab(self, *a, **k):
        raise _Captured(self)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", grab)
    try:
        cli.main()
    except _Captured as e:
        return e.args[0]
    raise AssertionError("main() never parsed args")


def test_cli_parser_tree_matches_golden(monkeypatch):
    got = json.loads(json.dumps(_describe(_capture_parser(monkeypatch)), sort_keys=True))
    if not GOLDEN.exists():  # one-off capture, run on the pre-split code
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    assert got == json.loads(GOLDEN.read_text())
