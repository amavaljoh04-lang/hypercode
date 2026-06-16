"""Interface de chat interactive — avec personnalité vivante."""

import asyncio
import os
import random
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


# ─── Phrases vivantes par contexte ───────────────────────────────────────────

PHRASES_WRITE = [
    "Allez, je crée ce fichier...",
    "Je code ça maintenant, regarde...",
    "Voilà ce que je mets dedans :",
    "Je te prépare ça, un instant...",
    "Hop, j'écris le fichier :",
    "C'est parti, voici le code :",
    "Je pose ça ici :",
    "Je génère le fichier, check :",
]

PHRASES_BASH = [
    "Je lance cette commande...",
    "Voyons ce que ça donne...",
    "J'exécute ça, on va voir...",
    "Go, je teste :",
    "Un petit coup de terminal...",
    "Je fais tourner ça :",
    "Exécution en cours...",
]

PHRASES_READ = [
    "Je jette un œil au fichier...",
    "Laisse-moi lire ça...",
    "Je regarde ce qu'il y a dedans...",
    "Voyons voir le contenu...",
    "Je check le fichier...",
]

PHRASES_SEARCH = [
    "Je fouille dans le code...",
    "Recherche en cours...",
    "Je cherche ça...",
    "Voyons si je trouve...",
]

PHRASES_WEB = [
    "Je cherche sur internet...",
    "Un petit tour sur le web...",
    "Je regarde ce qu'on trouve en ligne...",
    "Recherche web en cours...",
]

PHRASES_EDIT = [
    "Je modifie ce bout de code...",
    "Petite correction ici...",
    "Je retouche ça...",
    "Modification en cours...",
]

PHRASES_SUCCESS = [
    "Nickel, c'est bon !",
    "Parfait, ça marche !",
    "Impeccable !",
    "C'est fait !",
    "Top, aucun souci.",
    "Ça roule !",
    "Validé !",
]

PHRASES_ERROR = [
    "Hmm, ça a foiré... Je regarde pourquoi.",
    "Oups, erreur. Je corrige ça.",
    "Ah, problème ici. Laisse-moi voir...",
    "Pas bon ça... je cherche une solution.",
    "Raté. Je réessaie autrement.",
    "Erreur détectée, je m'en occupe.",
]

PHRASES_THINKING = [
    "Je réfléchis...",
    "Hmm, laisse-moi analyser ça...",
    "Je prépare la suite...",
    "Un instant, je cogite...",
    "Analyse en cours...",
    "Je planifie la prochaine étape...",
    "Cerveau en mode turbo...",
    "Concentration maximale...",
]

PHRASES_GIT = [
    "Un petit coup de git...",
    "Gestion de version en cours...",
    "Je commit ça proprement...",
]

PHRASES_TODO = [
    "Je mets à jour le plan...",
    "Tracking de la progression...",
    "Check-list mise à jour !",
]

PHRASES_TREE = [
    "Je regarde la structure du projet...",
    "Voyons l'arborescence...",
    "Check de la structure...",
]

PHRASES_HTTP = [
    "Je teste l'endpoint...",
    "Requête HTTP en cours...",
    "Je ping le serveur...",
]

PHRASES_LINT = [
    "Vérification qualité du code...",
    "Je passe le linter...",
    "Check des conventions...",
]

PHRASES_TEST = [
    "Lancement des tests...",
    "On vérifie que tout passe...",
    "Tests en cours...",
]

PHRASES_DOCKER = [
    "Docker en action...",
    "Containerisation en cours...",
]

PHRASES_DONE = [
    "Et voilà, c'est terminé ! 🎉",
    "Mission accomplie ! Tout est en place.",
    "Fini ! Regarde le résultat.",
    "C'est bouclé ! Dis-moi si tu veux que je modifie quelque chose.",
    "Terminé ! Le projet est prêt.",
]

TOOL_PHRASES = {
    "bash": PHRASES_BASH,
    "write": PHRASES_WRITE,
    "multiwrite": PHRASES_WRITE,
    "edit": PHRASES_EDIT,
    "patch": PHRASES_EDIT,
    "replace": PHRASES_EDIT,
    "read": PHRASES_READ,
    "search": PHRASES_SEARCH,
    "find": PHRASES_SEARCH,
    "web": PHRASES_WEB,
    "http": PHRASES_HTTP,
    "download": PHRASES_WEB,
    "git": PHRASES_GIT,
    "todo": PHRASES_TODO,
    "tree": PHRASES_TREE,
    "lint": PHRASES_LINT,
    "test": PHRASES_TEST,
    "docker": PHRASES_DOCKER,
    "think": PHRASES_THINKING,
}

ICONS = {
    "bash": "🔧", "write": "📝", "multiwrite": "📝", "edit": "✏️ ",
    "read": "📖", "search": "🔍", "web": "🌐", "git": "📦",
    "todo": "📋", "tree": "🌳", "find": "🔎", "http": "🌐",
    "process": "⚙️ ", "docker": "🐳", "lint": "🧹", "test": "🧪",
    "diff": "📊", "patch": "🩹", "replace": "🔄", "ssh": "🔑",
    "database": "🗄️ ", "env": "⚙️ ", "download": "⬇️ ", "archive": "📦",
    "think": "💭", "clipboard": "📋",
}


class ChatInterface:
    """Interface de chat interactive avec l'agent."""

    def __init__(self, model: str, agent_name: str = "coder"):
        self.model = model
        self.agent_name = agent_name
        self.agent = get_agent(agent_name)
        self.config = load_config()
        self.engine: Engine | None = None
        self._init_engine()
        self._last_tool_phrases: dict[str, str] = {}
        self._step_count = 0

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

    def _say(self, message: str, style: str = "italic dim white"):
        """L'agent 'dit' quelque chose de naturel."""
        console.print(f"\n  [bold bright_cyan]💬[/] [{style}]{message}[/]")

    def _pick_phrase(self, tool_name: str) -> str:
        """Choisit une phrase contextuelle sans répéter la dernière."""
        phrases = TOOL_PHRASES.get(tool_name, [f"J'utilise {tool_name}..."])
        last = self._last_tool_phrases.get(tool_name)
        choices = [p for p in phrases if p != last] or phrases
        phrase = random.choice(choices)
        self._last_tool_phrases[tool_name] = phrase
        return phrase

    def _detect_language(self, file_path: str) -> str:
        """Détecte le langage à partir de l'extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".md": "markdown", ".sh": "bash", ".bash": "bash",
            ".rs": "rust", ".go": "go", ".java": "java", ".c": "c",
            ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
            ".php": "php", ".sql": "sql", ".xml": "xml", ".svg": "xml",
            ".jsx": "jsx", ".tsx": "tsx", ".vue": "vue",
            ".dockerfile": "dockerfile", ".tf": "hcl", ".lua": "lua",
        }
        name = os.path.basename(file_path).lower()
        if name == "dockerfile":
            return "dockerfile"
        _, ext = os.path.splitext(name)
        return ext_map.get(ext, "text")

    def _render_code(self, content: str, file_path: str, max_lines: int = 60):
        """Affiche du code avec coloration syntaxique dans un panel."""
        lang = self._detect_language(file_path)
        lines = content.split("\n")
        total = len(lines)

        if total > max_lines:
            preview = "\n".join(lines[:40]) + f"\n\n  ... ({total - 50} lignes masquées) ...\n\n" + "\n".join(lines[-10:])
        else:
            preview = content

        console.print(Panel(
            Syntax(preview, lang, theme="monokai", line_numbers=True, word_wrap=True),
            title=f"[bold cyan]📄 {file_path}[/] [dim]({total} lignes)[/]",
            border_style="cyan",
            padding=(0, 1),
        ))

    def _handle_event(self, event: EngineEvent):
        """Gère les événements du moteur avec personnalité."""
        if event.type == "thinking":
            step = event.data.get("step", 0)
            self._step_count = step
            phrase = random.choice(PHRASES_THINKING)
            if step == 1:
                console.print(f"\n  [bold bright_cyan]🧠[/] [italic dim]{phrase}[/]  [dim cyan](étape {step})[/]")
            else:
                console.print(f"\n  [dim]{'─' * 50}[/]")
                console.print(f"  [bold bright_cyan]🧠[/] [italic dim]{phrase}[/]  [dim cyan](étape {step})[/]")

        elif event.type == "content":
            text = event.data.get("text", "")
            duration = event.data.get("duration", 0)
            tps = event.data.get("tokens_per_second", 0)

            if text.strip():
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
            icon = ICONS.get(name, "⚙️ ")

            # Phrase vivante avant l'action
            self._say(self._pick_phrase(name))

            if name == "bash":
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]{icon} bash →[/]")
                console.print(Panel(
                    Syntax(cmd, "bash", theme="monokai", word_wrap=True),
                    border_style="yellow",
                    padding=(0, 1),
                ))

            elif name in ("write", "multiwrite"):
                if name == "write":
                    path = args.get("file_path", "")
                    content = args.get("content", "")
                    console.print(f"  [bold yellow]{icon} write →[/] [white]{path}[/]")
                    if content:
                        self._render_code(content, path)
                elif name == "multiwrite":
                    files = args.get("files", [])
                    console.print(f"  [bold yellow]{icon} multiwrite →[/] [white]{len(files)} fichier(s)[/]")
                    for f in files:
                        if isinstance(f, dict):
                            fpath = f.get("path", "")
                            fcontent = f.get("content", "")
                            if fcontent:
                                self._render_code(fcontent, fpath)

            elif name == "edit":
                path = args.get("file_path", "")
                old = args.get("old_text", "")
                new = args.get("new_text", "")
                console.print(f"  [bold yellow]{icon} edit →[/] [white]{path}[/]")
                if old and new:
                    lang = self._detect_language(path)
                    console.print(Panel(
                        Syntax(f"- {old}\n+ {new}", lang, theme="monokai", word_wrap=True),
                        title="[red]ancien[/] → [green]nouveau[/]",
                        border_style="yellow",
                        padding=(0, 1),
                    ))

            elif name == "read":
                path = args.get("file_path", "")
                console.print(f"  [bold yellow]{icon} read →[/] [white]{path}[/]")

            elif name == "search":
                pat = args.get("pattern", "")
                console.print(f"  [bold yellow]{icon} search →[/] [white]{pat}[/]")

            elif name == "web":
                action = args.get("action", "")
                query = args.get("query", args.get("url", ""))
                console.print(f"  [bold yellow]{icon} web {action} →[/] [white]{query}[/]")

            elif name == "git":
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]{icon} git →[/] [white]{cmd}[/]")

            elif name == "todo":
                action = args.get("action", "")
                task = args.get("task", "")
                console.print(f"  [bold yellow]{icon} todo {action} →[/] [white]{task}[/]")

            elif name == "think":
                thought = args.get("thought", "")
                preview = thought[:300] + "..." if len(thought) > 300 else thought
                console.print(f"  [bold yellow]{icon} réflexion[/]")
                console.print(Panel(
                    preview,
                    border_style="dim magenta",
                    padding=(0, 1),
                ))

            elif name == "http":
                method = args.get("method", "GET")
                url = args.get("url", "")
                console.print(f"  [bold yellow]{icon} {method} →[/] [white]{url}[/]")

            elif name == "tree":
                path = args.get("path", ".")
                console.print(f"  [bold yellow]{icon} tree →[/] [white]{path}[/]")

            elif name == "docker":
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]{icon} docker →[/] [white]{cmd}[/]")

            elif name == "lint":
                path = args.get("path", "")
                console.print(f"  [bold yellow]{icon} lint →[/] [white]{path}[/]")

            elif name == "test":
                path = args.get("path", "")
                console.print(f"  [bold yellow]{icon} test →[/] [white]{path}[/]")

            elif name == "process":
                action = args.get("action", "")
                console.print(f"  [bold yellow]{icon} process {action}[/]")

            elif name == "diff":
                fa = args.get("file_a", "")
                console.print(f"  [bold yellow]{icon} diff →[/] [white]{fa}[/]")

            elif name == "ssh":
                host = args.get("host", "")
                cmd = args.get("command", "")
                console.print(f"  [bold yellow]{icon} ssh {host} →[/] [white]{cmd}[/]")

            elif name == "download":
                url = args.get("url", "")
                console.print(f"  [bold yellow]{icon} download →[/] [white]{url}[/]")

            elif name == "database":
                action = args.get("action", "")
                console.print(f"  [bold yellow]{icon} database {action}[/]")

            elif name == "archive":
                action = args.get("action", "")
                path = args.get("path", "")
                console.print(f"  [bold yellow]{icon} archive {action} →[/] [white]{path}[/]")

            elif name == "env":
                action = args.get("action", "")
                vname = args.get("name", "")
                console.print(f"  [bold yellow]{icon} env {action} →[/] [white]{vname}[/]")

            else:
                summary = str(args)[:120]
                console.print(f"  [bold yellow]{icon} {name} →[/] [dim]{summary}[/]")

        elif event.type == "tool_result":
            name = event.data.get("name", "")
            success = event.data.get("success", False)
            output = event.data.get("output", "")
            icon_ok = "[green]✓[/]"
            icon_fail = "[red]✗[/]"

            if not output:
                if success:
                    console.print(f"  {icon_ok} [italic dim]{random.choice(PHRASES_SUCCESS)}[/]")
                else:
                    console.print(f"  {icon_fail}")
                return

            # Réaction vivante aux résultats
            if success:
                reaction = random.choice(PHRASES_SUCCESS)
            else:
                reaction = random.choice(PHRASES_ERROR)

            if name == "bash" and output:
                display = output[:2000] + "\n[...tronqué]" if len(output) > 2000 else output
                console.print(Panel(
                    Syntax(display, "bash", theme="monokai", word_wrap=True),
                    title=f"{'✅' if success else '❌'} [dim]résultat[/]",
                    border_style="dim green" if success else "dim red",
                    padding=(0, 1),
                ))
                console.print(f"  [italic dim]{reaction}[/]")

            elif name == "read" and output:
                lines = output.count("\n") + 1
                console.print(f"  {icon_ok} [dim]Lu {lines} lignes — OK[/]")

            elif name == "tree" and output:
                console.print(Panel(
                    output[:3000],
                    title=f"{'✅' if success else '❌'} [dim]arborescence[/]",
                    border_style="dim cyan",
                    padding=(0, 1),
                ))

            elif name == "search" and output:
                display = output[:1500] + "\n[...tronqué]" if len(output) > 1500 else output
                console.print(Panel(
                    display,
                    title=f"{'✅' if success else '❌'} [dim]résultats[/]",
                    border_style="dim yellow",
                    padding=(0, 1),
                ))

            elif name == "http" and output:
                display = output[:2000] + "\n[...tronqué]" if len(output) > 2000 else output
                console.print(Panel(
                    display,
                    title=f"{'✅' if success else '❌'} [dim]réponse HTTP[/]",
                    border_style="dim blue",
                    padding=(0, 1),
                ))
                console.print(f"  [italic dim]{reaction}[/]")

            elif name in ("write", "multiwrite", "edit", "patch", "replace"):
                lines_info = output.split("\n")[0] if output else ""
                console.print(f"  {icon_ok if success else icon_fail} {lines_info}")
                if success:
                    console.print(f"  [italic dim]{reaction}[/]")

            elif name == "todo":
                console.print(f"  {icon_ok} [dim]{output}[/]")

            elif name == "think":
                console.print(f"  {icon_ok} [italic dim]Réflexion enregistrée[/]")

            elif name == "web":
                display = output[:1500] + "\n[...tronqué]" if len(output) > 1500 else output
                console.print(Panel(
                    display,
                    title=f"{'✅' if success else '❌'} [dim]résultat web[/]",
                    border_style="dim blue",
                    padding=(0, 1),
                ))

            elif name == "lint":
                display = output[:2000] + "\n[...tronqué]" if len(output) > 2000 else output
                console.print(Panel(
                    display,
                    title=f"{'✅' if success else '❌'} [dim]résultat lint[/]",
                    border_style="dim green" if success else "dim red",
                    padding=(0, 1),
                ))
                console.print(f"  [italic dim]{reaction}[/]")

            elif name == "test":
                display = output[:3000] + "\n[...tronqué]" if len(output) > 3000 else output
                console.print(Panel(
                    display,
                    title=f"{'✅' if success else '❌'} [dim]résultat tests[/]",
                    border_style="dim green" if success else "dim red",
                    padding=(0, 1),
                ))
                console.print(f"  [italic dim]{reaction}[/]")

            else:
                display = output[:500] + "..." if len(output) > 500 else output
                console.print(f"  {icon_ok if success else icon_fail} [dim]{display}[/]")
                if not success:
                    console.print(f"  [italic dim]{reaction}[/]")

        elif event.type == "error":
            msg = event.data.get("message", "Erreur inconnue")
            console.print(f"\n  [bold red]❌ Erreur:[/] {msg}")
            console.print(f"  [italic dim]{random.choice(PHRASES_ERROR)}[/]\n")

        elif event.type == "done":
            steps = event.data.get("total_steps", 0)
            phrase = random.choice(PHRASES_DONE)
            console.print(f"\n  [dim]{'═' * 50}[/]")
            console.print(f"  [bold bright_green]{phrase}[/]")
            console.print(f"  [dim]{steps} étape(s) exécutée(s)[/]")
            console.print(f"  [dim]{'═' * 50}[/]\n")

    async def run(self):
        """Lance la boucle de chat interactive."""
        self._print_header()
        working_dir = os.getcwd()

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.prompt_session.prompt("\n ❯ "),
                )

                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_continue = await self._handle_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Petite phrase d'accusé de réception
                acks = [
                    "C'est parti !",
                    "OK, je m'en occupe !",
                    "Compris, je commence...",
                    "Bien reçu, en route !",
                    "Allez, au boulot !",
                    "Je prends ça en charge !",
                    "Roger ! J'attaque...",
                ]
                console.print(f"\n  [bold bright_green]⚡[/] [italic]{random.choice(acks)}[/]\n")

                await self.engine.run(user_input, working_dir=working_dir)

            except (KeyboardInterrupt, EOFError):
                console.print("\n\n  [dim italic]Salut ! À la prochaine 👋[/]\n")
                break

        if self.engine:
            await self.engine.close()

    async def _handle_command(self, command: str) -> bool:
        """Gère les commandes slash. Retourne False pour quitter."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            console.print("\n  [dim italic]Salut ! À la prochaine 👋[/]\n")
            return False

        elif cmd == "/agent":
            await self._handle_agent_command(arg)

        elif cmd == "/model":
            await self._handle_model_command(arg)

        elif cmd == "/config":
            self._show_config()

        elif cmd == "/agents":
            self._list_agents()

        elif cmd == "/tools":
            self._list_tools()

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
        table.add_column("Outils", style="dim", max_width=40)

        for info in list_agents():
            is_current = " ⭐" if info["name"] == self.agent_name else ""
            table.add_row(
                f"{info['name']}{is_current}",
                info["description"],
                f"{len(info['tools'])} outils",
            )

        console.print(table)

    def _list_tools(self):
        """Liste tous les outils disponibles."""
        from hypercode.tools import ALL_TOOLS
        table = Table(box=box.ROUNDED, border_style="cyan", header_style="bold cyan")
        table.add_column("Outil", style="bold white")
        table.add_column("Description", style="white")

        for tool in ALL_TOOLS:
            icon = ICONS.get(tool.name, "⚙️")
            table.add_row(f"{icon} {tool.name}", tool.description[:70])

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
            "  [cyan]/tools[/]              — Lister les outils\n"
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
        from hypercode.tools import ALL_TOOLS
        console.print(Panel(
            f"[bold]Modèle:[/] {self.model}\n"
            f"[bold]Agent:[/] {self.agent_name}\n"
            f"[bold]Outils:[/] {len(ALL_TOOLS)} disponibles\n"
            f"[bold]Ollama:[/] {self.config['ollama']['host']}\n"
            f"[bold]Contexte:[/] {self.config['ollama']['context_length']} tokens\n"
            f"[bold]Session:[/] {self.engine.session.id if self.engine else 'N/A'}",
            title="Status",
            border_style="green",
        ))

    def _print_header(self):
        """Affiche le header au lancement."""
        from hypercode.tools import ALL_TOOLS
        console.print()
        console.print(Panel(
            Text.from_markup(
                "[bold white]H Y P E R C O D E[/]\n"
                "[dim]Agent de développement autonome ultra-performant[/]\n\n"
                f"[cyan]Modèle:[/] [bold]{self.model}[/]  •  "
                f"[cyan]Agent:[/] [bold]{self.agent_name}[/]  •  "
                f"[cyan]Outils:[/] [bold]{len(ALL_TOOLS)}[/]\n\n"
                "[dim]Tape /help pour les commandes • /tools pour les outils • /quit pour quitter[/]"
            ),
            border_style="bright_cyan",
            padding=(1, 4),
        ))
