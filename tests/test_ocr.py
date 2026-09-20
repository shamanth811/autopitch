import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from autopitch.api import create_app
from autopitch.config import Settings
from autopitch.factory import build_ocr
from autopitch.parsing import DeckParseError, OcrClient, OcrError, OcrUnavailableError, read_slides
from autopitch.testing import make_pdf
from tests.test_api import _graph

KEYS = ["secret-key-aaaa", "secret-key-bbbb", "secret-key-cccc"]


class HttpError(Exception):
    def __init__(self, status_code: int, message: str = "error") -> None:
        super().__init__(message)
        self.status_code = status_code


def _pages(*texts: str):
    return SimpleNamespace(
        pages=[SimpleNamespace(index=i, markdown=t) for i, t in enumerate(texts)]
    )


class FakeMistral:
    """Stands in for the SDK client. `behaviour` is a value to return or an exception to raise."""

    def __init__(self, key: str, behaviour: dict, calls: list) -> None:
        self.ocr = SimpleNamespace(process=self._process)
        self._key, self._behaviour, self._calls = key, behaviour, calls

    def _process(self, model, document):
        assert document["document_url"].startswith("data:application/pdf;base64,")
        self._calls.append(self._key)
        outcome = self._behaviour[self._key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(behaviour: dict, clock=None, keys=KEYS):
    calls: list[str] = []
    now = [0.0]
    ocr = OcrClient(
        keys,
        client_factory=lambda k: FakeMistral(k, behaviour, calls),
        clock=clock or (lambda: now[0]),
    )
    return ocr, calls, now


def test_starts_on_a_different_key_each_call():
    ocr, calls, _ = _client({k: _pages("ok") for k in KEYS})
    for _ in range(4):
        ocr.ocr_pdf(b"%PDF-")
    assert calls == [KEYS[0], KEYS[1], KEYS[2], KEYS[0]]


def test_moves_to_next_key_on_rate_limit_and_returns_its_result():
    ocr, calls, _ = _client(
        {KEYS[0]: HttpError(429), KEYS[1]: _pages("from b"), KEYS[2]: _pages("c")}
    )
    assert ocr.ocr_pdf(b"%PDF-") == ["from b"]
    assert calls == [KEYS[0], KEYS[1]]


def test_quota_message_without_status_counts_as_exhausted():
    ocr, calls, _ = _client(
        {
            KEYS[0]: HttpError(400, "Monthly quota exceeded"),
            KEYS[1]: _pages("b"),
            KEYS[2]: _pages("c"),
        }
    )
    assert ocr.ocr_pdf(b"%PDF-") == ["b"]


def test_exhausted_key_is_skipped_until_its_cooldown_ends():
    behaviour = {KEYS[0]: HttpError(429), KEYS[1]: _pages("b"), KEYS[2]: _pages("c")}
    ocr, calls, now = _client(behaviour)
    ocr.ocr_pdf(b"%PDF-")  # key 1 limited, key 2 answers
    calls.clear()
    ocr.ocr_pdf(b"%PDF-")  # rotation starts on key 2 anyway
    ocr.ocr_pdf(b"%PDF-")  # rotation starts on key 3
    ocr.ocr_pdf(b"%PDF-")  # rotation would start on key 1, but it is cooling down
    assert KEYS[0] not in calls

    # Cooldown over: key 1 is eligible again. Make the others fail so it has to be used.
    behaviour[KEYS[0]] = _pages("a again")
    behaviour[KEYS[1]] = behaviour[KEYS[2]] = HttpError(429)
    now[0] += 400  # past the 5 minute cooldown for rate limits
    calls.clear()
    assert ocr.ocr_pdf(b"%PDF-") == ["a again"]
    assert KEYS[0] in calls


def test_rejected_key_is_tried_last_resort_only():
    behaviour = {k: HttpError(401) for k in KEYS}
    ocr, calls, _ = _client(behaviour)
    with pytest.raises(OcrError) as err:
        ocr.ocr_pdf(b"%PDF-")
    assert calls == KEYS  # every key was tried once
    assert "key 1: rejected" in str(err.value)

    calls.clear()
    with pytest.raises(OcrError):
        ocr.ocr_pdf(b"%PDF-")  # all cooling, still attempted rather than refused
    assert len(calls) == 3


def test_all_keys_limited_raises_without_leaking_keys():
    ocr, _, _ = _client({k: HttpError(429) for k in KEYS})
    with pytest.raises(OcrError) as err:
        ocr.ocr_pdf(b"%PDF-")
    assert not any(k in str(err.value) for k in KEYS)


def test_bad_document_fails_immediately_without_burning_other_keys():
    ocr, calls, _ = _client({k: HttpError(422, "unreadable") for k in KEYS})
    with pytest.raises(OcrError):
        ocr.ocr_pdf(b"%PDF-")
    assert len(calls) == 1


def test_provider_outage_tries_next_key_without_cooldown():
    behaviour = {KEYS[0]: HttpError(503), KEYS[1]: _pages("b"), KEYS[2]: _pages("c")}
    ocr, calls, _ = _client(behaviour)
    assert ocr.ocr_pdf(b"%PDF-") == ["b"]
    behaviour[KEYS[0]] = _pages("a")
    calls.clear()
    ocr.ocr_pdf(b"%PDF-")
    ocr.ocr_pdf(b"%PDF-")
    ocr.ocr_pdf(b"%PDF-")
    assert KEYS[0] in calls  # an outage is not held against the key


def test_pages_come_back_in_order():
    resp = SimpleNamespace(
        pages=[SimpleNamespace(index=1, markdown="two"), SimpleNamespace(index=0, markdown="one")]
    )
    ocr, _, _ = _client({KEYS[0]: resp}, keys=KEYS[:1])
    assert ocr.ocr_pdf(b"%PDF-") == ["one", "two"]


# --- read_slides integration ---


class FakeOcr:
    def __init__(self, result: list[str] | Exception) -> None:
        self.result, self.sent = result, []

    def ocr_pdf(self, pdf: bytes) -> list[str]:
        self.sent.append(pdf)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_image_only_deck_is_read_through_ocr():
    ocr = FakeOcr(["# Zephyr", "# Traction ARR $310,000"])
    slides = read_slides(make_pdf(["", ""]), ocr=ocr)
    assert [(s.number, s.text) for s in slides] == [(1, "# Zephyr"), (2, "# Traction ARR $310,000")]


def test_only_pages_without_text_are_sent_to_ocr():
    ocr = FakeOcr(["# Scanned market slide"])
    slides = read_slides(make_pdf(["Problem slide", "", "Team slide"]), ocr=ocr)
    assert [s.number for s in slides] == [1, 2, 3]
    assert slides[0].text.startswith("Problem") and slides[1].text == "# Scanned market slide"
    assert len(PdfReader(io.BytesIO(ocr.sent[0])).pages) == 1  # just the blank page


def test_ocr_is_not_called_when_text_is_extractable():
    ocr = FakeOcr(["never"])
    read_slides(make_pdf(["Problem", "Market"]), ocr=ocr)
    assert ocr.sent == []


def test_without_ocr_image_only_deck_is_still_rejected():
    with pytest.raises(DeckParseError, match="OCR"):
        read_slides(make_pdf([""]), ocr=None)


def test_ocr_failure_keeps_text_pages_when_there_are_some():
    slides = read_slides(make_pdf(["Problem", ""]), ocr=FakeOcr(OcrError("down")))
    assert [s.number for s in slides] == [1]


def test_ocr_failure_on_a_fully_image_deck_is_reported_as_unavailable():
    with pytest.raises(OcrUnavailableError):
        read_slides(make_pdf(["", ""]), ocr=FakeOcr(OcrError("down")))


def test_page_limit_is_enforced_before_ocr():
    ocr = FakeOcr(["x"])
    with pytest.raises(DeckParseError, match="limit"):
        read_slides(make_pdf(["", "", ""]), max_pages=2, ocr=ocr)
    assert ocr.sent == []


# --- settings and API ---


def test_build_ocr_respects_keys_and_disable_flag():
    def s(**kw):
        return Settings(_env_file=None, **kw)

    assert build_ocr(s()) is None
    assert build_ocr(s(mistral_api_keys=" , ")) is None
    assert build_ocr(s(mistral_api_keys="a, b ,c", ocr_enabled=False)) is None
    assert isinstance(build_ocr(s(mistral_api_keys="a, b ,c")), OcrClient)


def _api(sample_deck, tmp_path, ocr):
    settings = Settings(_env_file=None, db_path=str(tmp_path / "t.db"))
    return TestClient(
        create_app(settings, lambda s: _graph(sample_deck), ocr_factory=lambda s: ocr),
        raise_server_exceptions=False,
    )


def _post(client, data):
    return client.post("/v1/analyze", files={"file": ("d.pdf", data, "application/pdf")})


def test_api_analyzes_an_image_only_deck_via_ocr(sample_deck, tmp_path):
    ocr = FakeOcr(["# Acme Grid seed deck"])
    r = _post(_api(sample_deck, tmp_path, ocr), make_pdf([""]))
    assert r.status_code == 200 and r.json()["deck"]["company"] == "Acme Grid"
    assert len(ocr.sent) == 1


def test_api_rejects_an_image_only_deck_when_ocr_is_off(sample_deck, tmp_path):
    r = _post(_api(sample_deck, tmp_path, None), make_pdf([""]))
    assert r.status_code == 422 and "OCR" in r.json()["detail"]


def test_api_reports_ocr_outage_as_502_without_details(sample_deck, tmp_path):
    ocr = FakeOcr(OcrError("key 1: limited; secret detail"))
    r = _post(_api(sample_deck, tmp_path, ocr), make_pdf([""]))
    assert r.status_code == 502 and "secret" not in r.text
