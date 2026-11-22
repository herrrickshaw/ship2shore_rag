"""ingest/sources.py network fetchers, with requests/time/PdfReader faked."""

import pytest
import requests

from ingest import sources


class Resp:
    def __init__(self, status=200, text="", content=b"", json_data=None, headers=None):
        self.status_code = status
        self.text = text
        self.content = content
        self._json = json_data
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(sources.time, "sleep", calls.append)
    return calls


def fake_get(monkeypatch, handler):
    """handler(url, **kw) -> Resp or raises. Returns the call log."""
    log = []

    def get(url, **kw):
        log.append((url, kw))
        return handler(url, **kw)

    monkeypatch.setattr(sources.requests, "get", get)
    return log


ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id> http://arxiv.org/abs/1 </id><title> Title One </title>
    <summary> Summary one </summary><published>2024-01-02T00:00:00Z</published></entry>
  <entry><id>http://arxiv.org/abs/2</id><title>No summary</title><summary></summary></entry>
  <entry><id></id><title>No id</title><summary>has summary</summary></entry>
  <entry><id>http://arxiv.org/abs/3</id><title>T3</title><summary>S3</summary></entry>
</feed>"""


# ---- arxiv ---------------------------------------------------------------------


def test_fetch_arxiv_parses_and_filters_entries(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: Resp(text=ATOM))
    docs = sources.fetch_arxiv("ship collision", max_results=3)
    assert [d["url"] for d in docs] == ["http://arxiv.org/abs/1", "http://arxiv.org/abs/3"]
    d = docs[0]
    assert d == {
        "source": "arxiv", "url": "http://arxiv.org/abs/1", "title": "Title One",
        "text": "Summary one", "license": "arXiv non-exclusive license",
        "published_at": "2024-01-02T00:00:00Z",
    }  # fmt: skip
    assert docs[1]["published_at"] is None
    url, kw = log[0]
    assert url == sources.ARXIV_API
    assert kw["params"] == {"search_query": "all:ship collision", "start": 0, "max_results": 3}
    assert kw["headers"] == sources.HEADERS and kw["timeout"] == 30
    assert sleeps == []


def test_fetch_arxiv_default_max_results(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: Resp(text=ATOM))
    sources.fetch_arxiv("q")
    assert log[0][1]["params"]["max_results"] == 20


def test_fetch_arxiv_retries_429_with_backoff_then_succeeds(monkeypatch, sleeps):
    responses = iter([Resp(429), Resp(429), Resp(text=ATOM)])
    log = fake_get(monkeypatch, lambda url, **kw: next(responses))
    docs = sources.fetch_arxiv("q")
    assert len(docs) == 2 and len(log) == 3
    assert sleeps == [10, 30]


def test_fetch_arxiv_gives_up_after_three_429s(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: Resp(429))
    with pytest.raises(requests.exceptions.HTTPError):
        sources.fetch_arxiv("q")
    assert len(log) == 3


def test_fetch_arxiv_non_429_error_does_not_retry(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: Resp(500))
    with pytest.raises(requests.exceptions.HTTPError):
        sources.fetch_arxiv("q")
    assert len(log) == 1 and sleeps == []


def test_fetch_arxiv_seed_dedupes_and_isolates_failures(monkeypatch, sleeps, capsys):
    def fake(query, n):
        if query == "bad":
            raise RuntimeError("down")
        return [
            {"url": "u1", "q": query},
            {"url": f"u-{query}", "q": query},
        ]

    monkeypatch.setattr(sources, "fetch_arxiv", fake)
    out = sources.fetch_arxiv_seed(["a", "bad", "b"], max_results_per_query=4)
    assert [d["url"] for d in out] == ["u1", "u-a", "u-b"]
    assert out[0]["q"] == "a"  # first sighting wins
    assert "skipping query 'bad': RuntimeError: down" in capsys.readouterr().out
    assert sleeps == [3, 3]  # polite delay only after queries that did not fail


def test_fetch_arxiv_seed_defaults(monkeypatch, sleeps):
    seen = []
    monkeypatch.setattr(sources, "fetch_arxiv", lambda q, n: seen.append((q, n)) or [])
    sources.fetch_arxiv_seed()
    assert [q for q, _ in seen] == sources.DEFAULT_ARXIV_QUERIES
    assert {n for _, n in seen} == {15}
    seen.clear()
    sources.fetch_arxiv_seed([])  # empty list falls back to the defaults too
    assert len(seen) == len(sources.DEFAULT_ARXIV_QUERIES)


# ---- wikipedia -------------------------------------------------------------------


def wiki_page(title, extract):
    return Resp(json_data={"query": {"pages": {"1": {"title": title, "extract": extract}}}})


def test_fetch_wikipedia_builds_docs(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: wiki_page("Bill of lading", "text body"))
    docs = sources.fetch_wikipedia(["Bill of lading"])
    assert docs == [
        {
            "source": "wikipedia",
            "url": "https://en.wikipedia.org/wiki/Bill_of_lading",
            "title": "Bill of lading",
            "text": "text body",
            "license": "CC BY-SA 4.0",
        }
    ]
    p = log[0][1]["params"]
    assert p["titles"] == "Bill of lading" and p["explaintext"] == 1 and p["format"] == "json"
    assert sleeps == [0.5]


def test_fetch_wikipedia_skips_empty_extracts_and_missing_query(monkeypatch, sleeps):
    pages = {
        "A": Resp(json_data={"query": {"pages": {"1": {"title": "A", "extract": ""}}}}),
        "B": Resp(json_data={}),
        "C": wiki_page("C", "ok"),
    }
    fake_get(monkeypatch, lambda url, **kw: pages[kw["params"]["titles"]])
    docs = sources.fetch_wikipedia(["A", "B", "C"])
    assert [d["title"] for d in docs] == ["C"]


def test_fetch_wikipedia_falls_back_to_requested_title(monkeypatch, sleeps):
    resp = Resp(json_data={"query": {"pages": {"1": {"extract": "x"}}}})
    fake_get(monkeypatch, lambda url, **kw: resp)
    docs = sources.fetch_wikipedia(["Port state control"])
    assert docs[0]["title"] == "Port state control"
    assert docs[0]["url"].endswith("/Port_state_control")


def test_fetch_wikipedia_rate_limit_retry_and_skip(monkeypatch, sleeps, capsys):
    responses = iter([Resp(429), Resp(429), Resp(429), wiki_page("Good", "g")])
    log = fake_get(monkeypatch, lambda url, **kw: next(responses))
    docs = sources.fetch_wikipedia(["Limited", "Good"])
    assert [d["title"] for d in docs] == ["Good"]
    assert len(log) == 4
    assert "skipping 'Limited': still rate-limited after retries" in capsys.readouterr().out
    assert sleeps[:2] == [5, 20]


def test_fetch_wikipedia_recovers_after_one_429(monkeypatch, sleeps):
    responses = iter([Resp(429), wiki_page("T", "x")])
    fake_get(monkeypatch, lambda url, **kw: next(responses))
    assert len(sources.fetch_wikipedia(["T"])) == 1
    assert sleeps == [5, 0.5]


def test_fetch_wikipedia_http_error_propagates(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(503))
    with pytest.raises(requests.exceptions.HTTPError):
        sources.fetch_wikipedia(["T"])


def test_fetch_wikipedia_defaults_to_curated_titles(monkeypatch, sleeps):
    log = fake_get(monkeypatch, lambda url, **kw: Resp(json_data={}))
    assert sources.fetch_wikipedia() == []
    assert [kw["params"]["titles"] for _, kw in log] == sources.DEFAULT_WIKIPEDIA_TITLES


# ---- pdf / reader ----------------------------------------------------------------


class FakePage:
    def __init__(self, text):
        self._t = text

    def extract_text(self):
        return self._t


def patch_reader(monkeypatch, pages):
    monkeypatch.setattr(
        sources, "PdfReader", lambda stream: type("R", (), {"pages": [FakePage(t) for t in pages]})
    )


def test_fetch_pdf_joins_pages_strips_nul_and_defaults(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(content=b"%PDF"))
    patch_reader(monkeypatch, ["page\x00 one", None, "page two"])
    doc = sources.fetch_pdf("http://x/dir/report.pdf")
    assert doc == {
        "source": "pdf",
        "url": "http://x/dir/report.pdf",
        "title": "report.pdf",
        "text": "page one\n\npage two",
        "license": "unspecified — verify before redistribution",
    }


def test_fetch_pdf_custom_title_and_license(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(content=b"x"))
    patch_reader(monkeypatch, ["t"])
    doc = sources.fetch_pdf("http://x/a.pdf", title="T", license="OGL")
    assert (doc["title"], doc["license"]) == ("T", "OGL")


def test_fetch_pdf_blank_text_returns_none(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(content=b"x"))
    patch_reader(monkeypatch, ["  ", "\x00", None])
    assert sources.fetch_pdf("http://x/a.pdf") is None


def test_fetch_pdf_retries_then_succeeds(monkeypatch, sleeps):
    responses = iter([requests.exceptions.ConnectionError("c"), Resp(500), Resp(content=b"x")])

    def handler(url, **kw):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    log = fake_get(monkeypatch, handler)
    patch_reader(monkeypatch, ["ok"])
    assert sources.fetch_pdf("http://x/a.pdf")["text"] == "ok"
    assert len(log) == 3 and sleeps == [5, 15]
    assert log[0][1]["timeout"] == 90


def test_fetch_pdf_raises_last_error_after_three_failures(monkeypatch, sleeps):
    errs = iter([requests.exceptions.Timeout("t1"), Resp(500), requests.exceptions.Timeout("t3")])

    def handler(url, **kw):
        r = next(errs)
        if isinstance(r, Exception):
            raise r
        return r

    fake_get(monkeypatch, handler)
    with pytest.raises(requests.exceptions.Timeout, match="t3"):
        sources.fetch_pdf("http://x/a.pdf")


def test_fetch_url_via_reader_success_and_dates(monkeypatch, sleeps):
    text = "Title: X\nPublished Time: 2024-03-15T12:00:00Z\n\nbody"
    log = fake_get(monkeypatch, lambda url, **kw: Resp(text=text))
    doc = sources.fetch_url_via_reader("http://site/page")
    assert log[0][0] == "https://r.jina.ai/http://site/page" and log[0][1]["timeout"] == 60
    assert doc["source"] == "pdf" and doc["title"] == "page" and doc["text"] == text
    assert doc["published_at"] == "2024-03-15T12:00:00Z"
    assert doc["license"] == "unspecified — verify before redistribution"


def test_fetch_url_via_reader_blank_returns_none_and_retries(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(text="   \n"))
    assert sources.fetch_url_via_reader("http://site/p") is None
    responses = iter([Resp(502), Resp(502), Resp(text="hello")])
    log = fake_get(monkeypatch, lambda url, **kw: next(responses))
    doc = sources.fetch_url_via_reader("http://site/p", title="TT", license="L")
    assert (doc["title"], doc["license"], doc["published_at"]) == ("TT", "L", None)
    assert len(log) == 3 and sleeps == [5, 20]


def test_fetch_url_via_reader_raises_last_error(monkeypatch, sleeps):
    fake_get(monkeypatch, lambda url, **kw: Resp(500))
    with pytest.raises(requests.exceptions.HTTPError):
        sources.fetch_url_via_reader("http://site/p")


def test_extract_reader_published_at_strips_whitespace():
    assert sources._extract_reader_published_at("Published Time:   2024-01-01  \nx") == "2024-01-01"
    assert sources._extract_reader_published_at("no header") is None


def test_fetch_pdf_sources_dispatches_on_type_and_isolates_errors(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "s.yaml"
    cfg.write_text(
        "pdf_sources:\n"
        "  - {url: http://a/1.pdf, title: One, license: L1}\n"
        "  - {url: http://b/page, type: html, title: Two}\n"
        "  - {url: http://c/bad.pdf}\n"
        "  - {url: http://d/empty.pdf}\n"
    )
    calls = []

    def fake_pdf(url, title, lic):
        calls.append(("pdf", url, title, lic))
        if "bad" in url:
            raise RuntimeError("nope")
        if "empty" in url:
            return None
        return {"url": url}

    def fake_html(url, title, lic):
        calls.append(("html", url, title, lic))
        return {"url": url}

    monkeypatch.setattr(sources, "fetch_pdf", fake_pdf)
    monkeypatch.setattr(sources, "fetch_url_via_reader", fake_html)
    out = sources.fetch_pdf_sources(str(cfg))
    assert out == [{"url": "http://a/1.pdf"}, {"url": "http://b/page"}]
    assert calls[0] == ("pdf", "http://a/1.pdf", "One", "L1")
    assert calls[1] == ("html", "http://b/page", "Two", None)
    assert "skipping http://c/bad.pdf: RuntimeError: nope" in capsys.readouterr().out


def test_fetch_pdf_sources_empty_config(tmp_path):
    cfg = tmp_path / "e.yaml"
    cfg.write_text("")
    assert sources.fetch_pdf_sources(str(cfg)) == []
    cfg.write_text("other: 1\n")
    assert sources.fetch_pdf_sources(str(cfg)) == []


# ---- maib / ntm ---------------------------------------------------------------------


MAIB_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title> R1 </title><updated>2025-01-01T00:00:00Z</updated>
    <link rel="alternate" href="http://gov/r1"/></entry>
  <entry><title>R2 non200</title><link rel="alternate" href="http://gov/r2"/></entry>
  <entry><title>R3 nopdf</title><link rel="alternate" href="http://gov/r3"/></entry>
  <entry><title>R4 nolink</title><link rel="self" href="http://gov/self"/></entry>
  <entry><title>R5 emptypdf</title><link rel="alternate" href="http://gov/r5"/></entry>
  <entry><title>R6</title><updated>2025-02-02T00:00:00Z</updated>
    <link rel="alternate" href="http://gov/r6"/></entry>
</feed>"""


def test_fetch_maib_pipeline(monkeypatch, sleeps):
    pages = {
        sources.MAIB_FEED: Resp(text=MAIB_FEED),
        "http://gov/r1": Resp(text='<a href="http://pdf/r1.pdf">x</a>'),
        "http://gov/r2": Resp(404, text='<a href="http://pdf/r2.pdf">'),
        "http://gov/r3": Resp(text="<p>no pdf here</p>"),
        "http://gov/r5": Resp(text='<a href="http://pdf/r5.pdf">'),
        "http://gov/r6": Resp(text='<a href="http://pdf/r6.pdf">'),
    }
    log = fake_get(monkeypatch, lambda url, **kw: pages[url])
    fetched = []

    def fake_pdf(url, title=None, license=None):
        fetched.append((url, title, license))
        if "r5" in url:
            return None
        return {"source": "pdf", "url": url, "title": title}

    monkeypatch.setattr(sources, "fetch_pdf", fake_pdf)
    out = sources.fetch_maib()
    assert [d["url"] for d in out] == ["http://pdf/r1.pdf", "http://pdf/r6.pdf"]
    assert all(d["source"] == "maib" for d in out)
    assert out[0]["published_at"] == "2025-01-01T00:00:00Z"
    assert out[1]["published_at"] == "2025-02-02T00:00:00Z"
    assert fetched[0] == ("http://pdf/r1.pdf", "R1", "Open Government Licence v3.0")
    assert "http://gov/self" not in [u for u, _ in log]  # entries without alternate link skipped


def test_fetch_maib_max_results_slices_entries(monkeypatch, sleeps):
    pages = {
        sources.MAIB_FEED: Resp(text=MAIB_FEED),
        "http://gov/r1": Resp(text='<a href="http://pdf/r1.pdf">'),
    }
    log = fake_get(monkeypatch, lambda url, **kw: pages[url])
    monkeypatch.setattr(sources, "fetch_pdf", lambda url, title=None, license=None: {"url": url})
    out = sources.fetch_maib(max_results=1)
    assert len(out) == 1 and len(log) == 2


def test_fetch_ntm_only_weekly_booklets(monkeypatch, sleeps):
    html = (
        "DownloadFile?fileName=36wknm26.pdf&amp;batchId=aa-11&amp;mimeType=x "
        "DownloadFile?fileName=Chart1.pdf&amp;batchId=aa-11&amp;mimeType=x "
        "DownloadFile?fileName=37wknm26.pdf&amp;batchId=aa-11&amp;mimeType=x"
    )
    fake_get(monkeypatch, lambda url, **kw: Resp(text=html))
    fetched = []

    def fake_pdf(url, title=None, license=None):
        fetched.append((url, title, license))
        return {"source": "pdf", "url": url} if "37" in url else None

    monkeypatch.setattr(sources, "fetch_pdf", fake_pdf)
    out = sources.fetch_ntm()
    assert len(fetched) == 2  # chart PDF is never fetched
    assert fetched[0][0] == (
        f"{sources.UKHO_NTM_DOWNLOAD}?fileName=36wknm26.pdf&batchId=aa-11"
        "&mimeType=application%2Fpdf&frequency=Weekly"
    )
    assert fetched[0][1] == "ADMIRALTY Notices to Mariners — Weekly Edition (36wknm26.pdf)"
    assert [d["source"] for d in out] == ["ntm"] and "37wknm26" in out[0]["url"]
    out = sources.fetch_ntm(max_results=1)
    assert len(out) == 0  # the single permitted booklet (36) yielded no text


# ---- ntsb ------------------------------------------------------------------------------


def case(report_no, city="Houston", state="TX", report_date="2025-05-05"):
    fields = []
    if report_no is not None:
        fields.append({"FieldName": "ReportNumber", "Values": [report_no]})
    if city is not None:
        fields.append({"FieldName": "City", "Values": [city]})
    if state is not None:
        fields.append({"FieldName": "State", "Values": [state]})
    if report_date is not None:
        fields.append({"FieldName": "ReportDate", "Values": [report_date]})
    return {"Fields": fields}


class FakeSession:
    def __init__(self, cases, head_map=None, post_codes=(200,)):
        self.headers = {}
        self.cases = cases
        self.head_map = head_map or {}
        self.post_codes = list(post_codes)
        self.posts = []
        self.template = {"QueryGroups": [{"QueryRules": [{"FieldName": "Mode", "Values": []}]}]}

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        if url.endswith("CreateSession"):
            code = self.post_codes.pop(0) if self.post_codes else 200
            return Resp(code, json_data="SESSION-1")
        return Resp(json_data={"Results": self.cases})

    def get(self, url, timeout=None):
        return Resp(json_data=self.template)

    def head(self, url, timeout=None, allow_redirects=None):
        r = self.head_map[url]
        if isinstance(r, Exception):
            raise r
        return r


def pdf_head():
    return Resp(200, headers={"Content-Type": "application/PDF"})


def test_fetch_ntsb_filters_reports_and_builds_docs(monkeypatch, sleeps, capsys):
    base = sources.NTSB_REPORT_BASE
    cases = [
        case("Closeout"),  # not a report number
        case(None),  # no ReportNumber field
        case("MIR2625"),
        case("MAR2105", city=None, state=None),
        case("MAB2126"),  # HEAD says html -> soft 404
        case("MIR2700"),  # HEAD is 404
        case("MIR2800"),  # HEAD raises
        case("MIR2900"),  # fetch_pdf raises
        case("MIR3000"),  # fetch_pdf returns None
    ]
    heads = {
        f"{base}/MIR2625.pdf": pdf_head(),
        f"{base}/MAR2105.pdf": pdf_head(),
        f"{base}/MAB2126.pdf": Resp(200, headers={"Content-Type": "text/html"}),
        f"{base}/MIR2700.pdf": Resp(404, headers={"Content-Type": "application/pdf"}),
        f"{base}/MIR2800.pdf": requests.exceptions.ConnectionError("boom"),
        f"{base}/MIR2900.pdf": pdf_head(),
        f"{base}/MIR3000.pdf": pdf_head(),
    }
    session = FakeSession(cases, heads)
    monkeypatch.setattr(sources.requests, "Session", lambda: session)

    def fake_pdf(url, title=None, license=None):
        if "2900" in url:
            raise RuntimeError("bad pdf")
        if "3000" in url:
            return None
        return {"source": "pdf", "url": url, "title": title, "license": license}

    monkeypatch.setattr(sources, "fetch_pdf", fake_pdf)
    out = sources.fetch_ntsb()
    assert [d["url"] for d in out] == [f"{base}/MIR2625.pdf", f"{base}/MAR2105.pdf"]
    assert out[0]["title"] == "NTSB Marine Accident Report MIR2625 — Houston, TX"
    assert out[1]["title"] == "NTSB Marine Accident Report MAR2105"  # no location suffix
    assert out[0]["published_at"] == "2025-05-05" and out[0]["source"] == "ntsb"
    assert out[0]["license"].startswith("U.S. government work")
    printed = capsys.readouterr().out
    assert "skipping MIR2800: ConnectionError: boom" in printed
    assert "skipping MIR2900: RuntimeError: bad pdf" in printed
    # the search was restricted to marine cases and carried the session id
    search_url, body = session.posts[-1]
    assert search_url.endswith("api/Query/Main")
    assert body["SessionId"] == "SESSION-1" and body["ResultSetOffset"] == 0
    assert session.template["QueryGroups"][0]["QueryRules"][0]["Values"] == ["Marine"]
    assert session.headers == sources.HEADERS


def test_fetch_ntsb_respects_max_results(monkeypatch, sleeps):
    base = sources.NTSB_REPORT_BASE
    cases = [case(f"MIR{2000 + i}") for i in range(5)]
    heads = {f"{base}/MIR{2000 + i}.pdf": pdf_head() for i in range(5)}
    monkeypatch.setattr(sources.requests, "Session", lambda: FakeSession(cases, heads))
    monkeypatch.setattr(sources, "fetch_pdf", lambda url, title=None, license=None: {"url": url})
    assert len(sources.fetch_ntsb(max_results=2)) == 2
    assert len(sources.fetch_ntsb(max_results=0)) == 0


def test_fetch_ntsb_falls_back_to_event_date(monkeypatch, sleeps):
    base = sources.NTSB_REPORT_BASE
    c = {
        "Fields": [
            {"FieldName": "ReportNumber", "Values": ["MIR2111"]},
            {"FieldName": "EventDate", "Values": ["2024-04-04"]},
        ]
    }
    monkeypatch.setattr(
        sources.requests, "Session",
        lambda: FakeSession([c], {f"{base}/MIR2111.pdf": pdf_head()}),
    )  # fmt: skip
    monkeypatch.setattr(sources, "fetch_pdf", lambda url, title=None, license=None: {"url": url})
    assert sources.fetch_ntsb()[0]["published_at"] == "2024-04-04"
    c["Fields"].pop()
    out = sources.fetch_ntsb()
    assert out[0]["published_at"] is None


def test_fetch_ntsb_retries_session_creation_on_429(monkeypatch, sleeps):
    session = FakeSession([], post_codes=(429, 429, 200))
    monkeypatch.setattr(sources.requests, "Session", lambda: session)
    assert sources.fetch_ntsb() == []
    assert sleeps == [10, 30]
    assert sum(1 for u, _ in session.posts if u.endswith("CreateSession")) == 3


def test_fetch_ntsb_session_failure_raises(monkeypatch, sleeps):
    session = FakeSession([], post_codes=(500,))
    monkeypatch.setattr(sources.requests, "Session", lambda: session)
    with pytest.raises(requests.exceptions.HTTPError):
        sources.fetch_ntsb()


@pytest.mark.parametrize(
    "number,ok",
    [("MIR2625", True), ("MAB2126", True), ("AB12", True), ("A1234", False), ("Closeout", False),
     ("MIR1", False), ("mir2625", False), ("MIR2625X", False), ("ABCDEF1234", False),
     ("ABCDE123456", True)],
)  # fmt: skip
def test_ntsb_report_number_regex_boundaries(number, ok):
    assert bool(sources.NTSB_REPORT_NUMBER_RE.match(number)) is ok
