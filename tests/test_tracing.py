import os

from autopitch.config import Settings
from autopitch.llm.fake import FakeLLM
from autopitch.schema import Slide
from autopitch.tracing import TracedLLM, configure_tracing


def test_tracing_disabled_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert configure_tracing(Settings(_env_file=None)) is False
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_tracing_enabled_with_key(monkeypatch):
    for var in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None, langsmith_api_key="ls-test", langsmith_project="ap-test")
    assert configure_tracing(s) is True
    assert os.environ["LANGSMITH_PROJECT"] == "ap-test"
    monkeypatch.setenv("LANGSMITH_TRACING", "false")  # keep the rest of the suite offline


def test_traced_llm_is_transparent(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    inner = FakeLLM({Slide: Slide(number=1, text="a")}, text="hello")
    llm = TracedLLM(inner)
    assert llm.generate("s", "p") == "hello"
    assert llm.generate_structured("s", "p", Slide).text == "a"
    assert llm.name == "fake"
