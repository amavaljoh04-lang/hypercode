"""Configuration persistante de HyperCode."""

import os
import yaml
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG = {
    "version": "0.1.0",
    "ollama": {
        "host": "http://localhost:11434",
        "model": None,
        "context_length": 16384,
        "temperature": 0.4,
    },
    "agent": {
        "default": "coder",
        "auto_approve": True,
        "max_retries": 3,
        "web_search_on_error": True,
    },
    "ui": {
        "theme": "dark",
        "show_thinking": True,
        "show_tool_calls": True,
        "language": "fr",
    },
    "permissions": {
        "bash": "allow",
        "edit": "allow",
        "write": "allow",
        "read": "allow",
        "web": "allow",
        "git": "allow",
    },
}


def get_config_dir() -> Path:
    """Retourne le répertoire de configuration."""
    config_dir = Path.home() / ".config" / "hypercode"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Retourne le chemin du fichier de configuration."""
    return get_config_dir() / "config.yaml"


def get_agents_dir() -> Path:
    """Retourne le répertoire des agents personnalisés."""
    agents_dir = get_config_dir() / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


def get_history_dir() -> Path:
    """Retourne le répertoire de l'historique des sessions."""
    history_dir = get_config_dir() / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


def load_config() -> dict:
    """Charge la configuration depuis le fichier YAML."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, "r") as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(DEFAULT_CONFIG.copy(), user_config)
    else:
        config = DEFAULT_CONFIG.copy()
        save_config(config)
    return config


def save_config(config: dict) -> None:
    """Sauvegarde la configuration dans le fichier YAML."""
    config_path = get_config_path()
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_value(key: str) -> Any:
    """Récupère une valeur de config par clé dotée (ex: 'ollama.model')."""
    config = load_config()
    keys = key.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return None
    return value


def set_value(key: str, value: Any) -> None:
    """Définit une valeur de config par clé dotée."""
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value
    save_config(config)


def _deep_merge(base: dict, override: dict) -> dict:
    """Fusionne récursivement deux dictionnaires."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
