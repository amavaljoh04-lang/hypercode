"""Barre de status pour l'interface."""

from rich.text import Text


def make_status_bar(model: str, agent: str, step: int = 0, tps: float = 0) -> Text:
    """Crée une barre de status formatée."""
    parts = []
    parts.append(f"⚡ {model}")
    parts.append(f"🤖 {agent}")
    if step > 0:
        parts.append(f"📊 step {step}")
    if tps > 0:
        parts.append(f"⚡ {tps:.1f} tok/s")
    return Text(" │ ".join(parts), style="dim cyan")
