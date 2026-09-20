"""Minimal SEC EDGAR client: full-text search and filing download.

SEC fair-access policy requires a descriptive User-Agent that identifies the requester and
a contact address, and caps traffic at 10 requests/second. Both are enforced here.
"""

from __future__ import annotations

import time
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel

_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{doc}"
_MIN_INTERVAL = 0.12  # seconds between requests, i.e. under 10 req/s


class FilingRef(BaseModel):
    company: str
    cik: str
    accession: str  # with dashes, e.g. 0001193125-21-123456
    document: str
    form: str
    filed: str  # ISO date

    @property
    def url(self) -> str:
        return _ARCHIVE_URL.format(
            cik=self.cik.lstrip("0"), adsh=self.accession.replace("-", ""), doc=self.document
        )


class EdgarClient:
    def __init__(self, user_agent: str) -> None:
        if "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent with a contact email, "
                'e.g. "Jane Doe jane@example.com". Set AUTOPITCH_SEC_USER_AGENT.'
            )
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=60.0,
            follow_redirects=True,
        )
        self._last = 0.0

    def _get(self, url: str, **params) -> httpx.Response:
        wait = _MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        resp = self._http.get(url, params=params or None)
        self._last = time.monotonic()
        resp.raise_for_status()
        return resp

    def search(
        self,
        query: str,
        forms: str = "S-1",
        start: str = "2015-01-01",
        end: str = "2025-12-31",
        limit: int = 20,
    ) -> list[FilingRef]:
        data = self._get(
            _SEARCH_URL, q=query, forms=forms, dateRange="custom", startdt=start, enddt=end
        ).json()
        refs: list[FilingRef] = []
        for hit in data.get("hits", {}).get("hits", []):
            src = hit["_source"]
            adsh, _, doc = hit["_id"].partition(":")
            if not doc or not src.get("ciks"):
                continue
            name = (src.get("display_names") or ["unknown"])[0].split("(")[0].strip()
            refs.append(
                FilingRef(
                    company=name,
                    cik=src["ciks"][0],
                    accession=adsh,
                    document=doc,
                    form=src.get("form", forms),
                    filed=src.get("file_date", ""),
                )
            )
            if len(refs) >= limit:
                break
        return refs

    def fetch_text(self, ref: FilingRef) -> str:
        return html_to_text(self._get(ref.url).text)


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head"}
    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)
