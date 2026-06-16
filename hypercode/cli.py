"""CLI principal de HyperCode."""

import asyncio
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel

from hypercode import __version__
from hypercode.config import load_config, set_value, get_value

console = Console()


BANNER = """
[bold bright_cyan]
    ██╗  ██╗██╗   ██╗██████╗ ███████╗██████╗  ██████╗ ██████╗ ██████╗ ███████╗
    ██║  ██║╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝
    ███████║ ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║     ██║   ██║██║  ██║█████╗
    ██╔══██║  ╚██╔╝  ██╔═══╝ ██╔══╝  ██╔══██╗██║     ██║   ██║██║  ██║██╔══╝
    ██║  ██║   ██║   ██║     ███████╗██║  ██║╚██████╗╚██████╔╝██████╔╝███████╗
    ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
[/]
[dim]                    Agent de développement autonome v{version}[/]
"""


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Affiche la version")
@click.pass_context
def main(ctx, version):
    """HyperCode — Agent de développement autonome ultra-performant."""
    if version:
        console.print(f"hypercode v{__version__}")
        return
    if ctx.invoked_subcommand is None:
        # Lancement par défaut = lancement interactif
        ctx.invoke(launch, provider="ollama")


@main.command()
@click.argument("provider", default="ollama")
@click.option("--host", "-h", default=None, help="Adresse du serveur Ollama")
@click.option("--model", "-m", default=None, help="Modèle à utiliser (skip la sélection)")
@click.option("--agent", "-a", default=None, help="Agent à utiliser (coder, planner, debugger, researcher)")
def launch(provider: str, host: str, model: str, agent: str):
    """Lance HyperCode en mode interactif.

    Usage: hypercode launch ollama
    """
    console.print(BANNER.format(version=__version__))

    config = load_config()

    # Configurer le host
    if host:
        set_value("ollama.host", host)
    ollama_host = host or config["ollama"]["host"]

    # Sélection ou récupération du modèle
    if model:
        selected_model = model
        set_value("ollama.model", model)
    else:
        saved_model = config["ollama"]["model"]
        if saved_model:
            # Vérifier que le modèle existe encore
            selected_model = saved_model
            console.print(f"  [dim]Modèle sauvegardé:[/] [bold green]{saved_model}[/]")
            console.print(f"  [dim]Utilise /model pour changer[/]\n")
        else:
            # Sélection interactive
            from hypercode.tui.model_select import select_model
            selected_model = asyncio.run(select_model(ollama_host))
            if not selected_model:
                console.print("  [red]Aucun modèle sélectionné. Quitte.[/]")
                sys.exit(1)

    # Sélection de l'agent
    agent_name = agent or config["agent"]["default"]

    # Lancer le chat
    from hypercode.tui.chat import ChatInterface
    chat = ChatInterface(model=selected_model, agent_name=agent_name)
    asyncio.run(chat.run())


@main.group()
def agent():
    """Gestion des agents."""
    pass


@agent.command("list")
def agent_list():
    """Liste les agents disponibles."""
    from hypercode.agents import list_agents
    from rich.table import Table
    from rich import box

    table = Table(box=box.ROUNDED, border_style="cyan", header_style="bold")
    table.add_column("Nom", style="bold cyan")
    table.add_column("Description")
    table.add_column("Outils", style="dim")

    for a in list_agents():
        table.add_row(a["name"], a["description"], ", ".join(a["tools"]))

    console.print(table)


@agent.command("use")
@click.argument("name")
def agent_use(name: str):
    """Définit l'agent par défaut."""
    from hypercode.agents import BUILTIN_AGENTS
    if name not in BUILTIN_AGENTS:
        console.print(f"[red]Agent inconnu: {name}[/]")
        console.print(f"[dim]Agents disponibles: {', '.join(BUILTIN_AGENTS.keys())}[/]")
        return
    set_value("agent.default", name)
    console.print(f"[green]✓[/] Agent par défaut: [bold]{name}[/]")


@agent.command("info")
@click.argument("name")
def agent_info(name: str):
    """Affiche les détails d'un agent."""
    from hypercode.agents import get_agent
    a = get_agent(name)
    console.print(Panel(
        f"[bold]{a.config.name}[/]\n\n"
        f"{a.config.description}\n\n"
        f"[dim]Outils:[/] {', '.join(a.config.tools)}\n"
        f"[dim]Température:[/] {a.config.temperature}\n"
        f"[dim]Max steps:[/] {a.config.max_steps}\n\n"
        f"[dim]Prompt system:[/]\n{a.config.system_prompt[:200]}...",
        title=f"Agent: {name}",
        border_style="blue",
    ))


@main.group()
def config():
    """Gestion de la configuration."""
    pass


@config.command("show")
def config_show():
    """Affiche la configuration actuelle."""
    import yaml
    from rich.syntax import Syntax
    cfg = load_config()
    console.print(Panel(
        Syntax(yaml.dump(cfg, default_flow_style=False), "yaml", theme="monokai"),
        title="Configuration HyperCode",
        border_style="blue",
    ))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Modifie une valeur de configuration. Ex: hypercode config set ollama.model gemma4:31b"""
    # Convertir les valeurs
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False
    elif value.isdigit():
        value = int(value)
    elif value.replace(".", "").isdigit():
        value = float(value)

    set_value(key, value)
    console.print(f"[green]✓[/] {key} = [bold]{value}[/]")


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """Affiche une valeur de configuration."""
    value = get_value(key)
    if value is not None:
        console.print(f"{key} = [bold]{value}[/]")
    else:
        console.print(f"[red]Clé non trouvée: {key}[/]")


@main.command()
def status():
    """Affiche le status du système (connexion Ollama, modèle, etc.)."""
    config = load_config()

    async def _check():
        from hypercode.core.llm import OllamaClient
        client = OllamaClient(config["ollama"]["host"])
        connected = await client.check_connection()
        models = await client.list_models() if connected else []
        running = await client.list_running() if connected else []
        await client.close()
        return connected, models, running

    connected, models, running = asyncio.run(_check())

    console.print(Panel(
        f"[bold]Ollama:[/] {'[green]connecté[/]' if connected else '[red]déconnecté[/]'} ({config['ollama']['host']})\n"
        f"[bold]Modèle:[/] {config['ollama']['model'] or '[dim]non défini[/]'}\n"
        f"[bold]Agent:[/] {config['agent']['default']}\n"
        f"[bold]Modèles installés:[/] {len(models)}\n"
        f"[bold]Modèles actifs:[/] {len(running)}\n"
        f"[bold]Contexte:[/] {config['ollama']['context_length']} tokens\n"
        f"[bold]Version:[/] {__version__}",
        title="[bold cyan]⚡ HyperCode Status[/]",
        border_style="cyan",
    ))


@main.command()
def models():
    """Liste les modèles Ollama disponibles."""
    from hypercode.tui.model_select import select_model
    asyncio.run(select_model())


if __name__ == "__main__":
    main()
