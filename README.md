# ⚡ HyperCode

**Agent de développement autonome ultra-performant.**

HyperCode surpasse OpenCode, OpenHands et Hermes en offrant un agent de développement local connecté à Ollama avec une interface terminal magnifique, des agents spécialisés, et une exécution autonome complète.

## 🚀 Installation

```bash
curl -fsSL https://raw.githubusercontent.com/amavaljoh04-lang/hypercode/main/install.sh | bash
```

Ou manuellement :
```bash
git clone https://github.com/amavaljoh04-lang/hypercode.git
cd hypercode
pip install -e .
```

## ⚡ Lancement

```bash
# Mode interactif (sélection du modèle puis chat)
hypercode

# Lancer directement avec Ollama
hypercode launch ollama

# Avec un modèle spécifique
hypercode launch ollama --model gemma4-31b-fast

# Avec un agent spécifique
hypercode launch ollama --agent debugger
```

## 🤖 Agents

| Agent | Rôle | Outils |
|-------|------|--------|
| **coder** | Développement principal — code, exécute, livre | bash, edit, read, write, search, git, web, todo |
| **planner** | Planification et architecture | read, search, web, todo |
| **debugger** | Diagnostic et résolution de bugs | bash, edit, read, search, web, todo |
| **researcher** | Recherche et documentation | web, read, search, todo |

## 🛠 Outils

- **bash** — Exécution de commandes shell (avec sudo)
- **edit** — Édition de fichiers (remplacement précis)
- **read** — Lecture de fichiers avec numéros de lignes
- **write** — Création de fichiers et dossiers
- **search** — Recherche dans le code (ripgrep)
- **git** — Opérations Git complètes
- **web** — Recherche internet + fetch d'URLs
- **todo** — Gestion des tâches et suivi de progression

## ⌨️ Commandes

### CLI
```bash
hypercode                      # Lancer en mode interactif
hypercode launch ollama        # Lancer avec Ollama
hypercode agent list           # Lister les agents
hypercode agent use <nom>      # Définir l'agent par défaut
hypercode config show          # Voir la configuration
hypercode config set key val   # Modifier une config
hypercode status               # Status du système
hypercode models               # Sélection de modèle
```

### Dans le chat
```
/agent list          — Liste les agents
/agent use <nom>     — Change d'agent
/model               — Changer de modèle
/model <nom>         — Utiliser un modèle spécifique
/config              — Afficher la configuration
/status              — Status du système
/history             — Historique des sessions
/help                — Aide
/clear               — Effacer l'écran
/quit                — Quitter
```

## ⚙️ Configuration

La config est sauvegardée dans `~/.config/hypercode/config.yaml` :

```yaml
ollama:
  host: http://localhost:11434
  model: gemma4-31b-fast        # Persiste après redémarrage !
  context_length: 16384
  temperature: 0.7

agent:
  default: coder
  auto_approve: true
  max_retries: 3
  web_search_on_error: true

permissions:
  bash: allow
  edit: allow
  write: allow
  read: allow
  web: allow
  git: allow
```

## 🏗 Architecture

```
hypercode/
├── cli.py              # Point d'entrée CLI
├── config.py           # Configuration persistante
├── core/
│   ├── engine.py       # Moteur agent (boucle + tool calling)
│   ├── llm.py          # Client Ollama API
│   └── memory.py       # Sessions et historique
├── agents/
│   ├── coder.py        # Agent développement
│   ├── planner.py      # Agent planification
│   ├── debugger.py     # Agent debug
│   └── researcher.py   # Agent recherche
├── tools/
│   ├── bash.py         # Exécution shell
│   ├── edit.py         # Édition fichiers
│   ├── read.py         # Lecture fichiers
│   ├── write.py        # Écriture fichiers
│   ├── search.py       # Recherche code
│   ├── git.py          # Opérations Git
│   ├── web.py          # Web search/fetch
│   └── todo.py         # Gestion tâches
└── tui/
    ├── model_select.py # Sélection de modèle
    └── chat.py         # Interface de chat
```

## 🔥 Pourquoi HyperCode > OpenCode ?

| Feature | OpenCode | HyperCode |
|---------|----------|-----------|
| **Agents spécialisés** | 2 (build, plan) | 4+ (coder, planner, debugger, researcher) |
| **Sélection modèle** | Menu basique | TUI interactive avec persistance |
| **Recherche web** | Non | Intégrée (DuckDuckGo) |
| **Prompt FR** | Non | Natif français |
| **Tool calling** | Limité | 8 outils complets |
| **Persistence config** | Partielle | Complète (YAML) |
| **Auto-approve** | Config | Par défaut |
| **Historique** | SQLite | JSON (portable) |
| **Installation** | Go binary | pip / one-liner |
| **Personnalisation** | Config JSON | Agents custom + YAML |

## 📋 Prérequis

- Python 3.10+
- Ollama installé et lancé
- Au moins un modèle téléchargé (ex: `ollama pull gemma4:31b`)

## 📝 Licence

MIT
