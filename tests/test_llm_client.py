import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generation.llm_client import LLMClient, _attendre_rate_limit, tronquer_messages


def test_attendre_rate_limit_parse_minutes_secondes():
    attente = _attendre_rate_limit("Please try again in 1m30.5s", tentative=0)
    assert 90 <= attente <= 120


def test_tronquer_messages_reduit_dernier_user():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "A" * 2000},
    ]
    out = tronquer_messages(msgs, facteur=0.5)
    assert out[0]["content"] == "sys"
    assert len(out[1]["content"]) < 2000
    assert "contexte tronqué" in out[1]["content"]


def test_llm_client_invoke_ok(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = LLMClient.__new__(LLMClient)
    client.modele = "llama-test"
    client.temperature = 0.2
    client.top_p = 0.9
    client.presence_penalty = 0.0
    client.frequency_penalty = 0.1
    client.max_tokens = 500
    client.modele_leger = False

    fake_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Bonjour"))],
        usage=SimpleNamespace(total_tokens=42),
    )
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = fake_completion

    texte, tokens = LLMClient.invoke(client, [{"role": "user", "content": "hi"}])
    assert texte == "Bonjour"
    assert tokens == 42


def test_llm_client_invoke_retry_413(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = LLMClient.__new__(LLMClient)
    client.modele = "llama-test"
    client.temperature = 0.2
    client.top_p = 0.9
    client.presence_penalty = 0.0
    client.frequency_penalty = 0.1
    client.max_tokens = 1000
    client.modele_leger = False

    ok = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
        usage=SimpleNamespace(total_tokens=10),
    )
    client.client = MagicMock()
    client.client.chat.completions.create.side_effect = [
        Exception("Request too large 413"),
        ok,
    ]

    texte, tokens = LLMClient.invoke(
        client,
        [{"role": "user", "content": "X" * 3000}],
        max_retries=3,
    )
    assert texte == "OK"
    assert tokens == 10
    assert client.max_tokens < 1000
