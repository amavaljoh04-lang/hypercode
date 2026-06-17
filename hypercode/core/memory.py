"""Gestion de la mémoire et de l'historique des conversations."""

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

from hypercode.core.llm import Message
from hypercode.config import get_history_dir


# Estimation grossière : 1 token ≈ 4 caractères en français/anglais
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estime le nombre de tokens d'un texte."""
    return len(text) // CHARS_PER_TOKEN


def truncate_content(content: str, max_chars: int = 2000) -> str:
    """Tronque un contenu long en gardant le début et la fin."""
    if len(content) <= max_chars:
        return content
    half = max_chars // 2
    return content[:half] + f"\n\n[...tronqué: {len(content)} chars total...]\n\n" + content[-half:]


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

    def get_messages_for_llm(self, max_tokens: int = 12000) -> list[Message]:
        """Retourne les messages formatés pour le LLM avec gestion du contexte.
        
        Stratégie :
        1. Toujours garder le system prompt (messages[0])
        2. Toujours garder la tâche initiale de l'utilisateur (messages[1])
        3. Remplir avec les messages récents en partant de la fin
        4. Tronquer les contenus longs (résultats d'outils, code)
        """
        valid = [m for m in self.messages if m["role"] in ("system", "user", "assistant")]
        if not valid:
            return []

        # System prompt = toujours inclus
        system_msg = valid[0] if valid[0]["role"] == "system" else None
        
        # Tâche initiale = premier message user après system
        initial_task = None
        other_messages = []
        found_task = False
        for m in valid[1:]:
            if not found_task and m["role"] == "user":
                initial_task = m
                found_task = True
            else:
                other_messages.append(m)

        # Calculer le budget tokens
        used = 0
        result = []

        if system_msg:
            used += estimate_tokens(system_msg["content"])
            result.append(Message(role="system", content=system_msg["content"]))

        if initial_task:
            used += estimate_tokens(initial_task["content"])
            result.append(Message(role="user", content=initial_task["content"]))

        # Remplir avec les messages récents (du plus récent au plus ancien)
        recent = []
        for m in reversed(other_messages):
            content = m["content"]
            
            # Compacter les messages assistant : retirer le contenu des <tool> (le code JSON)
            # pour ne garder que le texte visible + indication qu'il y avait des tools
            if m["role"] == "assistant":
                content = _compact_assistant_message(content)
            
            # Tronquer les résultats d'outils longs dans les messages user
            if m["role"] == "user" and len(content) > 3000:
                content = truncate_content(content, 2000)

            tokens = estimate_tokens(content)
            if used + tokens > max_tokens:
                # Plus de place — ajouter un résumé de transition
                break
            
            used += tokens
            recent.append(Message(role=m["role"], content=content))

        # Remettre dans l'ordre chronologique
        recent.reverse()
        
        # Si on a dû couper, ajouter un message de contexte
        if len(recent) < len(other_messages):
            skipped = len(other_messages) - len(recent)
            context_msg = (
                f"[{skipped} messages précédents omis pour le contexte. "
                f"Continue ta tâche en utilisant les outils <tool>.]"
            )
            result.append(Message(role="user", content=context_msg))

        result.extend(recent)
        return result

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


def _compact_assistant_message(content: str) -> str:
    """Compacte un message assistant pour économiser du contexte.
    
    Retire le contenu JSON des blocs <tool> (qui contient tout le code source)
    et le remplace par un résumé court.
    """
    import re
    
    def replace_tool(match):
        name = match.group(1)
        args_str = match.group(2).strip()
        
        # Parser les args pour extraire les infos clés
        try:
            args = json.loads(args_str)
        except (json.JSONDecodeError, ValueError):
            return f'<tool name="{name}">[paramètres]</tool>'
        
        if name == "write":
            path = args.get("file_path", "?")
            content = args.get("content", "")
            lines = content.count("\n") + 1
            return f'<tool name="write">{{"file_path": "{path}", "content": "[{lines} lignes]"}}</tool>'
        elif name == "multiwrite":
            files = args.get("files", [])
            summary = [f.get("path", "?") for f in files if isinstance(f, dict)]
            return f'<tool name="multiwrite">{{"files": [{", ".join(summary)}]}}</tool>'
        elif name == "bash":
            cmd = args.get("command", "")
            return f'<tool name="bash">{{"command": "{cmd[:100]}"}}</tool>'
        elif name == "edit":
            path = args.get("file_path", "?")
            return f'<tool name="edit">{{"file_path": "{path}"}}</tool>'
        else:
            # Garder compact
            short = json.dumps(args, ensure_ascii=False)
            if len(short) > 200:
                short = short[:200] + "..."
            return f'<tool name="{name}">{short}</tool>'
    
    pattern = r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>'
    compacted = re.sub(pattern, replace_tool, content, flags=re.DOTALL)
    return compacted


def generate_session_id() -> str:
    """Génère un ID de session unique."""
    import hashlib
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]
