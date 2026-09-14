"""Slice 3: reverse image search adapter — Yandex Images HTML, hybrid-only gate.

Reverse search sends the image to a third-party engine, so it must NEVER run in
local mode. When outside hybrid/approved mode the adapter reports blocked
honestly and makes no network call. Response bodies are untrusted; only link
extraction happens, links are weak evidence.
"""


import httpx

from tools.photo.reverse_search import YANDEX_UPLOAD_URL, ReverseImageSearchAdapter

_YANDEX_HTML = """
<html>
<body>
<div class="serp-item">
  <a class="serp-item__link" href="https://example.test/view/image1.jpg">i1</a>
</div>
<div class="serp-item">
  <a class="serp-item__link" href="https://other.test/gallery/image2">i2</a>
</div>
<a class="serp-item__link" href="https://example.test/view/image1.jpg">dup</a>
<div class="serp-item"><a href="https://example.test/about">no img context</a></div>
</body>
</html>
"""


def _make_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=_YANDEX_HTML)),
        follow_redirects=True,
    )


def test_adapter_is_in_photo_targets():
    a = ReverseImageSearchAdapter(client=_make_client(), allowed=True)
    assert a.target_types == ("image",)
    assert a.name == "photo-reverse-search"


def test_reverse_search_parses_links_as_weak_evidence(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0JFIF\x00synthetic-jpeg")
    a = ReverseImageSearchAdapter(client=_make_client(), allowed=True)
    res = a.run(str(img))
    assert res.status == "completed"
    urls = {f.url for f in res.findings}
    assert "https://example.test/view/image1.jpg" in urls
    assert "https://other.test/gallery/image2" in urls
    assert len(urls) == 2  # duplicate collapsed
    assert all(f.confidence == "weak" for f in res.findings)
    assert all(f.type == "image_exposure" for f in res.findings)
    assert res.coverage["note"].startswith("2")


def test_reverse_search_uploads_multipart_to_yandex(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0JFIF\x00synthetic-jpeg")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=_YANDEX_HTML)

    a = ReverseImageSearchAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        allowed=True,
    )
    a.run(str(img))
    assert captured["url"].startswith(YANDEX_UPLOAD_URL)


def test_reverse_search_blocked_in_local_mode_makes_no_request(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0JFIF\x00synthetic-jpeg")
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text=_YANDEX_HTML)

    a = ReverseImageSearchAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        allowed=False,
    )
    res = a.run(str(img))
    assert res.status == "blocked"
    assert called["n"] == 0
    assert any("hybrid" in (e or "") for e in (res.errors or []))


def test_reverse_search_missing_file_fails_honestly(tmp_path):
    a = ReverseImageSearchAdapter(client=_make_client(), allowed=True)
    res = a.run(str(tmp_path / "nope.jpg"))
    assert res.status == "failed"
    assert res.errors


def test_reverse_search_http_error_failed(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"junk")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    a = ReverseImageSearchAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        allowed=True,
    )
    res = a.run(str(img))
    assert res.status == "failed"


def test_reverse_search_results_json_fixture_supported(tmp_path):
    """Provider may return structured data instead of HTML; both must parse."""
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"junk")
    payload = {
        "matches": [
            {"url": "https://a.test/p/1", "similarity": 0.9},
            {"url": "https://b.test/post/2", "similarity": 0.8},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    a = ReverseImageSearchAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        allowed=True,
    )
    res = a.run(str(img))
    assert res.status == "completed"
    assert {f.url for f in res.findings} == {"https://a.test/p/1", "https://b.test/post/2"}
    assert res.raw_reference == "yandex"