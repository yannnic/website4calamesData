"""
Teste : le choix de la configuration du LLM (réglages du client, envoyés en en-têtes
X-LLM-*, sinon ceux du serveur), que la clé du serveur n'est jamais envoyée à une
URL choisie par le client, et /llm/check. Sans Elasticsearch ni appel réel au LLM.

    cd backend
    python -m pytest api/test_llm.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.llm as llm
import api.main as main


@pytest.fixture
def server_key(monkeypatch):
    monkeypatch.setattr(llm, "NL_LLM_API_KEY", "cle-serveur")
    monkeypatch.setattr(llm, "NL_LLM_BASE_URL", "https://serveur.example/v1")


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "call_llm", lambda config, *a, **k: seen.append(config) or '{"ok": true}')
    return seen


def test_client_settings_take_precedence(server_key):
    cfg = llm.llm_config("http://localhost:11434/v1", "", "mistral")
    assert (cfg.base_url, cfg.model, cfg.source) == ("http://localhost:11434/v1", "mistral", "client")
    assert cfg.enabled            # serveur local : pas de clé nécessaire


def test_server_key_never_goes_to_a_client_url(server_key):
    cfg = llm.llm_config("https://ailleurs.example/v1", "", "")
    assert cfg.api_key == ""
    cfg = llm.llm_config("", "", "autre-modele")
    assert (cfg.api_key, cfg.base_url) == ("", llm.DEFAULT_BASE_URL)
    assert not cfg.enabled        # OpenAI sans clé


def test_server_settings_without_client_settings(server_key):
    cfg = llm.llm_config()
    assert (cfg.api_key, cfg.base_url, cfg.source) == ("cle-serveur", "https://serveur.example/v1", "server")


def test_check_endpoint(monkeypatch, calls):
    monkeypatch.setattr(llm, "NL_LLM_API_KEY", "")
    client = TestClient(main.app)   # sans lifespan : pas d'Elasticsearch
    res = client.get("/llm/check").json()
    assert not res["ok"] and res["error"] == llm.NOT_CONFIGURED and not calls

    res = client.get("/llm/check", headers={"X-LLM-Api-Key": "sk-test", "X-LLM-Model": "gpt-test"}).json()
    assert res["ok"] and res["source"] == "client" and res["model"] == "gpt-test"
    assert calls[-1].api_key == "sk-test"
