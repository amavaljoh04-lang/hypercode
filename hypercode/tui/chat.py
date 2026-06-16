"""Interface de chat interactive."""

import asyncio
import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich import box
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from hypercode.core.engine import Engine, EngineEvent
from hypercode.agents import get_agent, list_agents, BUILTIN_AGENTS
from hypercode.config import load_config, get_config_dir, set_value


console = Console()


class ChatInterface:
    """Interface de chat interactive avec l'agent."""

    def __init__(self, model: str, agent_name: str = "coder"):
        self.model = model
        self.agent_name = agent_name
        self.agent = get_agent(agent_name)
        self.config = load_config()
        self.engine: Engine | None = None
        self._init_engine()

        # Historique des commandes
        history_file = get_config_dir() / "chat_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    def _init_engine(self):
        """Initialise le moteur avec l'agent courant."""
        self.engine = Engine(
            model=self.model,
            system_prompt=self.agent.get_system_prompt(),
            ollama_host=self.config["ollama"]["host"],
            on_event=self._handle_event,
        )

    def _handle_event(self, event: EngineEvent):
        """Gère les événements du moteur."""
        if event.type == "thinking":
            step = event.data.get("step", 0)
            console.print(f"  [dim cyan]⏳ Réflexion (étape {step})...[/]")

        elif event.type == "content":
            text = event.data.get("text", "")
            duration = event.data.get("duration", 0)
            tps = event.data.get("tokens_per_second", 0)

            console.print()
            console.print(Panel(
                Markdown(text),
                title=f"[bold green]🤖 {self.agent_name}[/]",
                subtitle=f"[dim]{duration:.1f}s • {tps:.1f} tok/s[/]" if duration else None,
                border_style="green",
                padding=(1, 2),
            ))

        elif event.type == "tool_call":
            name = event.data.get("name", "")
            args = event.data.get("arguments", {})
            # Affichage compact de l'appel d'outil
            if name == "bash":
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]🔧 bash →[/] [white]{cmd}[/]")
            elif name == "write":
                path = args.get("file_path", "")
                console.print(f"  [bold yellow]📝 write →[/] [white]{path}[/]")
            elif name == "edit":
                path = args.get("file_path", "")
                console.print(f"  [bold yellow]✏️  edit →[/] [white]{path}[/]")
            elif name == "read":
                path = args.get("file_path", "")
                console.print(f"  [bold yellow]📖 read →[/] [white]{path}[/]")
            elif name == "search":
                pat = args.get("pattern", "")
                console.print(f"  [bold yellow]🔍 search →[/] [white]{pat}[/]")
            elif name == "web":
                action = args.get("action", "")
                query = args.get("query", "")
                console.print(f"  [bold yellow]🌐 web {action} →[/] [white]{query}[/]")
            elif name == "git":
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]📦 git →[/] [white]{cmd}[/]")
            elif name == "todo":
                action = args.get("action", "")
                task = args.get("task", "")
                console.print(f"  [bold yellow]📋 todo {action} →[/] [white]{task}[/]")
            else:
                console.print(f"  [bold yellow]⚙️  {name} →[/] [dim]{args}[/]")

        elif event.type == "tool_result":
            name = event.data.get("name", "")
            success = event.data.get("success", False)
            output = event.data.get("output", "")

            if output:
                # Tronquer si trop long pour l'affichage
                display = output[:500] + "..." if len(output) > 500 else output
                icon = "[green]✓[/]" if success else "[red]✗[/]"
                console.print(f"  {icon} [dim]{display}[/]")
            else:
                icon = "[green]✓[/]" if success else "[red]✗[/]"
                console.print(f"  {icon}")

        elif event.type == "error":
            msg = event.data.get("message", "Erreur inconnue")
            console.print(f"\n  [bold red]❌ Erreur:[/] {msg}\n")

        elif event.type == "done":
            steps = event.data.get("total_steps", 0)
            console.print(f"\n  [dim]— Terminé en {steps} étape(s) —[/]\n")

    async def run(self):
        """Lance la boucle de chat interactive."""
        import os

        self._print_header()
        working_dir = os.getcwd()

        while True:
            try:
                # Prompt utilisateur
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.prompt_session.prompt(
                        f"\n [bold cyan]❯[/bold cyan] ",
                    ),
                )

                user_input = user_input.strip()
                if not user_input:
                    continue

                # Commandes spéciales
                if user_input.startswith("/"):
                    should_continue = await self._handle_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Exécuter via le moteur
                await self.engine.run(user_input, working_dir=working_dir)

            except (KeyboardInterrupt, EOFError):
                console.print("\n\n  [dim]Au revoir ![/]\n")
                break

        if self.engine:
            await self.engine.close()

    async def _handle_command(self, command: str) -> bool:
        """Gère les commandes slash. Retourne False pour quitter."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            console.print("\n  [dim]Au revoir ![/]\n")
            return False

        elif cmd == "/agent":
            await self._handle_agent_command(arg)

        elif cmd == "/model":
            await self._handle_model_command(arg)

        elif cmd == "/config":
            self._show_config()

        elif cmd == "/agents":
            self._list_agents()

        elif cmd == "/clear":
            console.clear()
            self._print_header()

        elif cmd == "/history":
            self._show_history()

        elif cmd == "/help":
            self._show_help()

        elif cmd == "/status":
            self._show_status()

        else:
            console.print(f"  [red]Commande inconnue: {cmd}[/] — tape [bold]/help[/] pour la liste")

        return True

    async def _handle_agent_command(self, arg: str):
        """Gère /agent [subcommand]."""
        parts = arg.split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"

        if sub == "list":
            self._list_agents()
        elif sub == "use":
            name = parts[1].strip() if len(parts) > 1 else ""
            if name in BUILTIN_AGENTS:
                self.agent_name = name
                self.agent = get_agent(name)
                self._init_engine()
                set_value("agent.default", name)
                console.print(f"  [green]✓[/] Agent changé: [bold]{name}[/]")
            else:
                console.print(f"  [red]Agent inconnu: {name}[/]")
                self._list_agents()
        elif sub == "info":
            name = parts[1].strip() if len(parts) > 1 else self.agent_name
            agent = get_agent(name)
            console.print(Panel(
                f"[bold]{agent.config.name}[/]\n\n"
                f"{agent.config.description}\n\n"
                f"[dim]Outils:[/] {', '.join(agent.config.tools)}\n"
                f"[dim]Température:[/] {agent.config.temperature}\n"
                f"[dim]Max étapes:[/] {agent.config.max_steps}",
                title=f"Agent: {name}",
                border_style="blue",
            ))
        else:
            console.print("  [dim]Usage: /agent list | /agent use <nom> | /agent info <nom>[/]")

    async def _handle_model_command(self, arg: str):
        """Gère /model [name]."""
        if arg:
            self.model = arg.strip()
            set_value("ollama.model", self.model)
            self._init_engine()
            console.print(f"  [green]✓[/] Modèle changé: [bold]{self.model}[/]")
        else:
            # Relancer la sélection
            from hypercode.tui.model_select import select_model
            new_model = await select_model()
            if new_model:
                self.model = new_model
                self._init_engine()

    def _show_config(self):
        """Affiche la configuration."""
        config = load_config()
        import yaml
        console.print(Panel(
            Syntax(yaml.dump(config, default_flow_style=False), "yaml", theme="monokai"),
            title="Configuration",
            border_style="blue",
        ))

    def _list_agents(self):
        """Liste les agents disponibles."""
        table = Table(box=box.ROUNDED, border_style="blue", header_style="bold cyan")
        table.add_column("Nom", style="bold white")
        table.add_column("Description", style="white")
        table.add_column("Outils", style="dim")

        for info in list_agents():
            is_current = " ⭐" if info["name"] == self.agent_name else ""
            table.add_row(
                f"{info['name']}{is_current}",
                info["description"],
                ", ".join(info["tools"]),
            )

        console.print(table)

    def _show_history(self):
        """Affiche l'historique de la session."""
        from hypercode.core.memory import Session
        sessions = Session.list_sessions()[:10]
        if not sessions:
            console.print("  [dim]Aucune session précédente[/]")
            return

        table = Table(box=box.ROUNDED, border_style="blue")
        table.add_column("ID", style="dim")
        table.add_column("Modèle", style="cyan")
        table.add_column("Agent", style="green")
        table.add_column("Messages", style="yellow", justify="right")

        for s in sessions:
            table.add_row(s["id"][:8], s["model"], s["agent"], str(s["messages_count"]))

        console.print(table)

    def _show_help(self):
        """Affiche l'aide."""
        console.print(Panel(
            "[bold]Commandes disponibles:[/]\n\n"
            "  [cyan]/agent list[/]         — Liste les agents\n"
            "  [cyan]/agent use <nom>[/]    — Change d'agent\n"
            "  [cyan]/agent info <nom>[/]   — Détails d'un agent\n"
            "  [cyan]/model[/]              — Changer de modèle\n"
            "  [cyan]/model <nom>[/]        — Utiliser un modèle spécifique\n"
            "  [cyan]/config[/]             — Afficher la configuration\n"
            "  [cyan]/history[/]            — Historique des sessions\n"
            "  [cyan]/status[/]             — Status du système\n"
            "  [cyan]/clear[/]              — Effacer l'écran\n"
            "  [cyan]/help[/]               — Cette aide\n"
            "  [cyan]/quit[/]               — Quitter\n\n"
            "[dim]Tape directement ton message pour parler à l'agent.[/]",
            title="[bold cyan]⚡ Aide HyperCode[/]",
            border_style="cyan",
        ))

    def _show_status(self):
        """Affiche le status."""
        console.print(Panel(
            f"[bold]Modèle:[/] {self.model}\n"
            f"[bold]Agent:[/] {self.agent_name}\n"
            f"[bold]Ollama:[/] {self.config['ollama']['host']}\n"
            f"[bold]Contexte:[/] {self.config['ollama']['context_length']} tokens\n"
            f"[bold]Session:[/] {self.engine.session.id if self.engine else 'N/A'}",
            title="Status",
            border_style="green",
        ))

    def _print_header(self):
        """Affiche le header au lancement."""
        console.print()
        console.print(Panel(
            Text.from_markup(
                "[bold white]H Y P E R C O D E[/]\n"
                "[dim]Agent de développement autonome ultra-performant[/]\n\n"
                f"[cyan]Modèle:[/] [bold]{self.model}[/]  •  "
                f"[cyan]Agent:[/] [bold]{self.agent_name}[/]\n\n"
                "[dim]Tape /help pour les commandes • /quit pour quitter[/]"
            ),
            border_style="bright_cyan",
            padding=(1, 4),
        ))
