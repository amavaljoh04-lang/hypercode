"""Test HyperCode — site web complexe avec Three.js (le test qui échouait avant)."""

import asyncio
import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hypercode.core.engine import Engine, EngineEvent
from hypercode.agents.coder import CODER_PROMPT
from hypercode.config import load_config


TASK = """Crée un site web immersif dans /workspace/complex-site/ avec :
- index.html avec une scène Three.js (particules 3D, rotation automatique)
- style.css avec un design futuriste dark theme
- main.js avec Three.js importé depuis CDN, une scène avec 500 particules qui bougent
- Un effet de parallax au scroll
- Un loader animé au chargement
Lance un serveur Python sur le port 9999. Vérifie que le site répond HTTP 200."""

events_log = []
start = time.time()
tool_calls = 0
tool_errors = 0
steps = 0


def on_event(event: EngineEvent):
    global tool_calls, tool_errors, steps
    t = round(time.time() - start, 1)
    events_log.append({"t": t, "type": event.type, "data": event.data})

    if event.type == "thinking":
        steps = event.data.get("step", steps)
        print(f"  [{t}s] Étape {steps}...")
    elif event.type == "tool_call":
        tool_calls += 1
        name = event.data.get("name", "?")
        args = event.data.get("arguments", {})
        if name == "write":
            info = args.get("file_path", "?")
        elif name == "bash":
            info = args.get("command", "?")[:60]
        else:
            info = str(args)[:60]
        print(f"    🔧 {name} → {info}")
    elif event.type == "tool_result":
        success = event.data.get("success", False)
        output = event.data.get("output", "")[:80]
        if not success:
            tool_errors += 1
        icon = "✓" if success else "✗"
        print(f"    {icon} {output}")
    elif event.type == "content":
        text = event.data.get("text", "")[:120]
        if text.strip():
            print(f"    💬 {text}")
    elif event.type == "error":
        print(f"    ❌ {event.data.get('message', '')}")
    elif event.type == "done":
        print(f"\n  Terminé — {steps} étapes, {tool_calls} outils, {tool_errors} erreurs, {t}s")


async def main():
    config = load_config()
    model = config["ollama"]["model"]
    print(f"Modèle: {model}")
    print(f"Contexte: {config['ollama']['context_length']}")
    print(f"Température: {config['ollama']['temperature']}")
    print(f"\nTâche: {TASK[:100]}...")
    print(f"\n{'='*60}")

    engine = Engine(
        model=model,
        system_prompt=CODER_PROMPT,
        ollama_host=config["ollama"]["host"],
        on_event=on_event,
    )

    try:
        await engine.run(TASK, working_dir="/workspace")
    except Exception as e:
        print(f"  ❌ Exception: {e}")
    finally:
        await engine.close()

    # Save log
    with open("/tmp/hypercode_test_complex_site.json", "w") as f:
        json.dump(events_log, f, indent=2, ensure_ascii=False)
    print(f"\n  📄 Log: /tmp/hypercode_test_complex_site.json")

    # Verify files
    print(f"\n  📁 Fichiers créés:")
    os.system("find /workspace/complex-site -type f 2>/dev/null | head -20")

    # Summary
    print(f"\n{'='*60}")
    print(f"  RÉSULTAT: {'✓ PASS' if tool_errors <= 2 else '✗ FAIL'}")
    print(f"  Étapes: {steps}, Outils: {tool_calls}, Erreurs: {tool_errors}")
    print(f"  Durée: {round(time.time() - start)}s")


if __name__ == "__main__":
    asyncio.run(main())
