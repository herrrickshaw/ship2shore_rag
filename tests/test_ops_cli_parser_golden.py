"""Characterisation: the full ops_cli argparse tree (flags, choices, defaults,
help, handler names) is pinned to a golden file captured before the split."""

import argparse
import json
from pathlib import Path

import ops_cli

GOLDEN = Path(__file__).with_name("golden_ops_cli_parser.json")


def _describe(parser):
    out = []
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            subs = {}
            helps = {ca.dest: ca.help for ca in a._choices_actions}
            for name, sp in a.choices.items():
                subs[name] = {"help": helps.get(name), "parser": _describe(sp)}
            out.append({"subparsers": subs, "dest": a.dest, "required": a.required})
        else:
            out.append(
                {
                    "opts": list(a.option_strings),
                    "dest": a.dest,
                    "default": a.default,
                    "choices": list(a.choices) if a.choices else None,
                    "type": getattr(a.type, "__name__", None),
                    "required": a.required,
                    "help": a.help,
                    "nargs": a.nargs,
                    "const": a.const,
                    "kind": type(a).__name__,
                }
            )
    func = parser.get_default("func")
    return {"actions": out, "func": getattr(func, "__name__", None)}


def test_ops_cli_parser_tree_matches_golden():
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    ops_cli.register(sub)
    got = json.loads(json.dumps(_describe(root), sort_keys=True))
    if not GOLDEN.exists():  # one-off capture, run on the pre-split code
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    assert got == json.loads(GOLDEN.read_text())
