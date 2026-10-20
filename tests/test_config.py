from pathlib import Path

from market_agent import config


def test_home_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_AGENT_HOME", str(tmp_path))
    assert config._home() == tmp_path.resolve()


def test_home_defaults_to_source_checkout(monkeypatch):
    monkeypatch.delenv("MARKET_AGENT_HOME", raising=False)
    assert (config._home() / "pyproject.toml").exists()
    assert config._home() == Path(config.__file__).resolve().parents[2]
