"""Test complet de HyperCode — 3 types de tâches."""

import asyncio
import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hypercode.core.engine import Engine, EngineEvent
from hypercode.agents.coder import CODER_PROMPT
from hypercode.config import load_config


# ─── Configuration ───
OLLAMA_HOST = "http://localhost:11434"
MODEL = None  # Auto-detect from config
TESTS = []

# ─── Test 1: Site web statique ───
TESTS.append({
    "name": "website",
    "task": (
        "Crée un site web portfolio dans /workspace/test-site/ avec :\n"
        "- index.html avec un header, 3 sections (À propos, Projets, Contact)\n"
        "- style.css avec un design moderne (dark theme, glassmorphism)\n"
        "- main.js avec un effet de particules simple en canvas\n"
        "Lance un serveur Python sur le port 7771. Vérifie avec HTTP que ça répond."
    ),
})

# ─── Test 2: Application Python CLI ───
TESTS.append({
    "name": "app-cli",
    "task": (
        "Crée une application CLI Python dans /workspace/test-app/ :\n"
        "- app.py : un outil CLI qui prend un fichier texte et affiche des stats "
        "(nombre de mots, lignes, caractères, mot le plus fréquent)\n"
        "- Crée un fichier test.txt avec du contenu de test\n"
        "- Exécute app.py sur test.txt et vérifie que ça fonctionne"
    ),
})

# ─── Test 3: Débogage ───
TESTS.append({
    "name": "debug",
    "task": (
        "Débogue ce script Python. Crée-le dans /workspace/test-debug/broken.py :\n"
        "```\n"
        "import json\n"
        "def parse_config(path):\n"
        "    with open(path) as f:\n"
        "        data = json.load(f)\n"
        "    return data['server']['host'], data['server']['port']\n\n"
        "def start_server(host, port):\n"
        "    print(f'Starting on {host}:{port}')\n"
        "    for i in range(10):\n"
        "        print(f'Request {i}: {process_request(i)}')\n\n"
        "def process_request(n):\n"
        "    results = []\n"
        "    for i in range(n):\n"
        "        results.append(i * 2)\n"
        "    return sum(results) / len(results)\n\n"
        "host, port = parse_config('config.json')\n"
        "start_server(host, port)\n"
        "```\n"
        "Il y a 2 bugs : 1) config.json n'existe pas, 2) division par zéro quand n=0.\n"
        "Crée le fichier, crée config.json, corrige les 2 bugs, et exécute pour vérifier."
    ),
})


class TestLogger:
    """Logger qui capture tous les événements."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.events = []
        self.start_time = time.time()
        self.tool_calls = 0
        self.tool_errors = 0
        self.steps = 0

    def on_event(self, event: EngineEvent):
        elapsed = time.time() - self.start_time
        self.events.append({
            "time": round(elapsed, 1),
            "type": event.type,
            "data": event.data,
        })

        if event.type == "thinking":
            self.steps = event.data.get("step", self.steps)
            print(f"  [{self.test_name}] Étape {self.steps}...")

        elif event.type == "tool_call":
            self.tool_calls += 1
            name = event.data.get("name", "?")
            args = event.data.get("arguments", {})
            # Show compact args
            if name == "write":
                info = args.get("file_path", "?")
            elif name == "bash":
                info = args.get("command", "?")[:80]
            elif name == "http":
                info = args.get("url", "?")
            else:
                info = str(args)[:80]
            print(f"    🔧 {name} → {info}")

        elif event.type == "tool_result":
            success = event.data.get("success", False)
            output = event.data.get("output", "")[:100]
            icon = "✓" if success else "✗"
            if not success:
                self.tool_errors += 1
            print(f"    {icon} {output}")

        elif event.type == "content":
            text = event.data.get("text", "")[:200]
            if text.strip():
                print(f"    💬 {text[:150]}")

        elif event.type == "error":
            print(f"    ❌ ERREUR: {event.data.get('message', '')}")

        elif event.type == "done":
            total = event.data.get("total_steps", 0)
            elapsed = time.time() - self.start_time
            print(f"  [{self.test_name}] Terminé — {total} étapes, {self.tool_calls} outils, "
                  f"{self.tool_errors} erreurs, {elapsed:.0f}s")

    def get_summary(self) -> dict:
        elapsed = time.time() - self.start_time
        return {
            "test": self.test_name,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "duration_s": round(elapsed, 1),
            "events_count": len(self.events),
        }


async def run_test(test: dict) -> dict:
    """Exécute un test et retourne le rapport."""
    name = test["name"]
    task = test["task"]

    print(f"\n{'='*60}")
    print(f"  TEST: {name}")
    print(f"{'='*60}")

    config = load_config()
    model = MODEL or config["ollama"]["model"]
    if not model:
        print("  ❌ Aucun modèle configuré. Utilisez 'hypercode config set ollama.model NOM'")
        return {"test": name, "error": "no model"}

    logger = TestLogger(name)

    engine = Engine(
        model=model,
        system_prompt=CODER_PROMPT,
        ollama_host=OLLAMA_HOST,
        on_event=logger.on_event,
    )

    try:
        result = await engine.run(task, working_dir="/workspace")
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return {"test": name, "error": str(e)}
    finally:
        await engine.close()

    summary = logger.get_summary()

    # Save events log
    log_path = f"/tmp/hypercode_test_{name}.json"
    with open(log_path, "w") as f:
        json.dump(logger.events, f, indent=2, ensure_ascii=False)
    print(f"  📄 Log sauvé: {log_path}")

    return summary


async def main():
    # Clean workspace
    os.makedirs("/workspace", exist_ok=True)

    # Run selected tests or all
    test_names = sys.argv[1:] if len(sys.argv) > 1 else [t["name"] for t in TESTS]

    results = []
    for test in TESTS:
        if test["name"] in test_names:
            r = await run_test(test)
            results.append(r)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  RÉSUMÉ")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['test']}: ERREUR — {r['error']}")
        else:
            status = "✓ OK" if r["tool_errors"] == 0 else f"⚠ {r['tool_errors']} erreurs"
            print(f"  {status} | {r['test']} — {r['steps']} étapes, "
                  f"{r['tool_calls']} outils, {r['duration_s']}s")


if __name__ == "__main__":
    asyncio.run(main())
