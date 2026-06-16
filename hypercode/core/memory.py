"""Gestion de la mémoire et de l'historique des conversations."""

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

from hypercode.core.llm import Message
from hypercode.config import get_history_dir


@dataclass
class Session:
    """Une session de conversation."""
    id: str
    model: str
    agent: str
    working_dir: str
    created_at: float = field(default_factory=time.time)
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs):
        """Ajoute un message à la session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **kwargs,
        }
        self.messages.append(msg)

    def get_messages_for_llm(self) -> list[Message]:
        """Retourne les messages formatés pour le LLM."""
        return [
            Message(role=m["role"], content=m["content"])
            for m in self.messages
            if m["role"] in ("system", "user", "assistant", "tool")
        ]

    def save(self):
        """Sauvegarde la session sur disque."""
        session_file = get_history_dir() / f"{self.id}.json"
        with open(session_file, "w") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, session_id: str) -> Optional["Session"]:
        """Charge une session depuis le disque."""
        session_file = get_history_dir() / f"{session_id}.json"
        if not session_file.exists():
            return None
        with open(session_file, "r") as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def list_sessions(cls) -> list[dict]:
        """Liste toutes les sessions sauvegardées."""
        sessions = []
        for f in get_history_dir().glob("*.json"):
            try:
                with open(f, "r") as fp:
                    data = json.load(fp)
                sessions.append({
                    "id": data["id"],
                    "model": data["model"],
                    "agent": data["agent"],
                    "created_at": data["created_at"],
                    "messages_count": len(data.get("messages", [])),
                })
            except Exception:
                continue
        return sorted(sessions, key=lambda x: x["created_at"], reverse=True)


def generate_session_id() -> str:
    """Génère un ID de session unique."""
    import hashlib
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]
