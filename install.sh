#!/bin/bash
# HyperCode — Installation automatique
# Usage: curl -fsSL https://raw.githubusercontent.com/amavaljoh04-lang/hypercode/main/install.sh | bash

set -e

BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}"
echo "    ██╗  ██╗██╗   ██╗██████╗ ███████╗██████╗  ██████╗ ██████╗ ██████╗ ███████╗"
echo "    ██║  ██║╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝"
echo "    ███████║ ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║     ██║   ██║██║  ██║█████╗  "
echo "    ██╔══██║  ╚██╔╝  ██╔═══╝ ██╔══╝  ██╔══██╗██║     ██║   ██║██║  ██║██╔══╝  "
echo "    ██║  ██║   ██║   ██║     ███████╗██║  ██║╚██████╗╚██████╔╝██████╔╝███████╗"
echo "    ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝"
echo -e "${RESET}"
echo -e "${DIM}              Agent de développement autonome ultra-performant${RESET}"
echo ""

# Vérifier Python >= 3.10
echo -e "${CYAN}[1/4]${RESET} Vérification de Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 non trouvé. Installe Python 3.10+ d'abord.${RESET}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}Python $PYTHON_VERSION détecté. Python 3.10+ requis.${RESET}"
    exit 1
fi
echo -e "  ${GREEN}✓${RESET} Python $PYTHON_VERSION"

# Vérifier pip
echo -e "${CYAN}[2/4]${RESET} Vérification de pip..."
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${DIM}  Installation de pip...${RESET}"
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3
fi
echo -e "  ${GREEN}✓${RESET} pip OK"

# Installer HyperCode
echo -e "${CYAN}[3/4]${RESET} Installation de HyperCode..."

INSTALL_DIR="${HOME}/.hypercode"
mkdir -p "$INSTALL_DIR"

# Cloner ou mettre à jour
if [ -d "$INSTALL_DIR/src" ]; then
    echo -e "  ${DIM}Mise à jour...${RESET}"
    cd "$INSTALL_DIR/src"
    git pull --quiet 2>/dev/null || true
else
    echo -e "  ${DIM}Téléchargement...${RESET}"
    git clone --quiet https://github.com/amavaljoh04-lang/hypercode.git "$INSTALL_DIR/src"
    cd "$INSTALL_DIR/src"
fi

# Installer avec pip
python3 -m pip install -e "$INSTALL_DIR/src" --quiet --break-system-packages 2>/dev/null || \
python3 -m pip install -e "$INSTALL_DIR/src" --quiet

echo -e "  ${GREEN}✓${RESET} HyperCode installé"

# Vérifier que le binaire est dans le PATH
echo -e "${CYAN}[4/4]${RESET} Configuration du PATH..."

BIN_PATH=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))")

if ! echo "$PATH" | grep -q "$BIN_PATH"; then
    # Ajouter au PATH
    SHELL_RC=""
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        echo "" >> "$SHELL_RC"
        echo "# HyperCode" >> "$SHELL_RC"
        echo "export PATH=\"$BIN_PATH:\$PATH\"" >> "$SHELL_RC"
        echo -e "  ${GREEN}✓${RESET} PATH mis à jour dans $SHELL_RC"
        echo -e "  ${DIM}Relance ton terminal ou: source $SHELL_RC${RESET}"
    fi
fi

# Vérifier Ollama
echo ""
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓${RESET} Ollama détecté"
else
    echo -e "${DIM}ℹ Ollama non détecté. Installe-le: curl -fsSL https://ollama.com/install.sh | sh${RESET}"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ Installation terminée !${RESET}"
echo ""
echo -e "  ${BOLD}Lancer HyperCode:${RESET}"
echo -e "    ${CYAN}hypercode${RESET}                    — Mode interactif"
echo -e "    ${CYAN}hypercode launch ollama${RESET}      — Lancer avec Ollama"
echo -e "    ${CYAN}hypercode agent list${RESET}         — Voir les agents"
echo -e "    ${CYAN}hypercode status${RESET}             — Status du système"
echo ""
echo -e "  ${BOLD}Commandes dans le chat:${RESET}"
echo -e "    ${CYAN}/agent use coder${RESET}    — Changer d'agent"
echo -e "    ${CYAN}/model${RESET}              — Changer de modèle"
echo -e "    ${CYAN}/help${RESET}               — Aide complète"
echo ""
