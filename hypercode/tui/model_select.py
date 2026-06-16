"""Sélection interactive du modèle Ollama."""

import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import IntPrompt
from rich import box

from hypercode.core.llm import OllamaClient
from hypercode.config import load_config, set_value, get_value


console = Console()


def format_size(size_bytes: int) -> str:
    """Formate une taille en bytes en format lisible."""
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    elif size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    return f"{size_bytes / 1_000:.1f} KB"


async def select_model(ollama_host: str = None) -> str | None:
    """Affiche la sélection interactive du modèle et retourne le modèle choisi."""
    config = load_config()
    host = ollama_host or config["ollama"]["host"]
    saved_model = config["ollama"]["model"]

    client = OllamaClient(host=host)

    # Vérifier la connexion
    console.print()
    with console.status("[bold cyan]Connexion à Ollama...[/]"):
        connected = await client.check_connection()

    if not connected:
        console.print(Panel(
            f"[red bold]Impossible de se connecter à Ollama[/]\n\n"
            f"Adresse: {host}\n\n"
            f"Vérifie que Ollama est lancé:\n"
            f"  [dim]ollama serve[/]",
            title="❌ Erreur de connexion",
            border_style="red",
        ))
        await client.close()
        return None

    # Récupérer les modèles
    models = await client.list_models()
    running = await client.list_running()
    await client.close()

    if not models:
        console.print(Panel(
            "[yellow]Aucun modèle trouvé sur Ollama.[/]\n\n"
            "Installe un modèle:\n"
            "  [dim]ollama pull gemma4:31b[/]",
            title="⚠️ Aucun modèle",
            border_style="yellow",
        ))
        return None

    running_names = {m.get("name", "") for m in running}

    # Afficher le header
    console.print()
    console.print(Panel(
        "[bold white]Sélection du modèle[/]",
        title="[bold cyan]⚡ HyperCode[/]",
        border_style="cyan",
        padding=(0, 2),
    ))

    # Si un modèle est déjà sauvegardé, proposer de le réutiliser
    if saved_model:
        model_exists = any(m.get("name") == saved_model for m in models)
        if model_exists:
            console.print(f"\n  [dim]Modèle précédent:[/] [bold green]{saved_model}[/]")
            console.print(f"  [dim]Appuie sur Entrée pour le réutiliser, ou choisis un autre:[/]\n")

    # Table des modèles
    table = Table(
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold cyan",
        row_styles=["", "dim"],
    )
    table.add_column("#", style="bold white", width=4, justify="right")
    table.add_column("Modèle", style="bold white", min_width=30)
    table.add_column("Taille", style="yellow", width=10, justify="right")
    table.add_column("Quantization", style="magenta", width=12)
    table.add_column("Status", style="green", width=10)

    for i, model in enumerate(models, 1):
        name = model.get("name", "?")
        size = format_size(model.get("size", 0))
        quant = model.get("details", {}).get("quantization_level", "?")
        is_running = "🟢 actif" if name in running_names else ""
        is_saved = " ⭐" if name == saved_model else ""

        table.add_row(
            str(i),
            f"{name}{is_saved}",
            size,
            quant,
            is_running,
        )

    console.print(table)
    console.print()

    # Sélection
    while True:
        try:
            default_idx = None
            if saved_model:
                for i, m in enumerate(models, 1):
                    if m.get("name") == saved_model:
                        default_idx = i
                        break

            prompt_text = f"Choisis un modèle [1-{len(models)}]"
            if default_idx:
                prompt_text += f" (défaut: {default_idx})"

            choice = console.input(f"  [bold cyan]›[/] {prompt_text}: ").strip()

            if not choice and default_idx:
                idx = default_idx
            else:
                idx = int(choice)

            if 1 <= idx <= len(models):
                selected = models[idx - 1]["name"]
                set_value("ollama.model", selected)
                console.print(f"\n  [bold green]✓[/] Modèle sélectionné: [bold]{selected}[/]")
                console.print(f"  [dim]Sauvegardé — sera réutilisé automatiquement au prochain lancement[/]\n")
                return selected

            console.print(f"  [red]Choix invalide. Entre un nombre entre 1 et {len(models)}[/]")

        except (ValueError, KeyboardInterrupt):
            if KeyboardInterrupt:
                console.print("\n  [dim]Annulé[/]")
                return None
            console.print(f"  [red]Entre un nombre valide[/]")
