"""Renders an ask() result as a compact, standalone report — small enough to
paste into an email body or attach directly. No external assets (fonts,
stylesheets, JS), so it stays small and renders the same in any mail client."""
import html as html_lib


def render_html(question: str, answer: str | None, passages: list[dict]) -> str:
    if answer:
        body = f'<h2>Answer</h2><p>{html_lib.escape(answer).replace(chr(10), "<br>")}</p>'
    else:
        items = "".join(
            f'<div class="passage"><p><b>[{i}] {html_lib.escape(p["title"])}</b></p>'
            f'<p>{html_lib.escape(p["content"][:600])}{"..." if len(p["content"]) > 600 else ""}</p></div>'
            for i, p in enumerate(passages, 1)
        )
        body = f"<h2>Retrieved passages</h2>{items}"

    sources = "".join(
        f'<li><a href="{html_lib.escape(p["url"])}">{html_lib.escape(p["title"])}</a> '
        f'<span class="score">score {p["score"]:.3f}</span></li>'
        for p in passages
    )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html_lib.escape(question)}</title>"
        "<style>"
        "body{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:640px;"
        "margin:24px auto;padding:0 16px;color:#222;line-height:1.5}"
        "h1{font-size:19px} h2{font-size:14px;color:#555;margin-top:22px;"
        "text-transform:uppercase;letter-spacing:.04em}"
        ".score{color:#888;font-size:12px} .passage{margin-bottom:14px}"
        "ul{padding-left:18px} a{color:#155}"
        "</style></head><body>"
        f"<h1>{html_lib.escape(question)}</h1>"
        f"{body}"
        f"<h2>Sources</h2><ul>{sources}</ul>"
        "</body></html>"
    )


def render_text(question: str, answer: str | None, passages: list[dict]) -> str:
    lines = [question, "=" * len(question), ""]
    if answer:
        lines += [answer, ""]
    else:
        for i, p in enumerate(passages, 1):
            lines += [f"[{i}] {p['title']}", p["content"][:600].strip(), ""]
    lines.append("Sources:")
    for i, p in enumerate(passages, 1):
        lines.append(f"[{i}] {p['title']} — {p['url']} (score {p['score']:.3f})")
    return "\n".join(lines)


RENDERERS = {
    "html": render_html,
    "txt": render_text,
    "md": render_text,
}


def export(result: dict, question: str, path: str, fmt: str | None = None) -> int:
    """Writes the report to `path` (format inferred from its extension unless
    `fmt` is given). Returns the file size in bytes."""
    fmt = fmt or path.rsplit(".", 1)[-1].lower()
    renderer = RENDERERS.get(fmt)
    if renderer is None:
        raise ValueError(f"unknown export format: {fmt} (supported: {', '.join(RENDERERS)})")
    content = renderer(question, result["answer"], result["passages"])
    with open(path, "w") as f:
        f.write(content)
    return len(content.encode("utf-8"))
