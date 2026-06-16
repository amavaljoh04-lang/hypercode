"""Outil de recherche et remplacement dans plusieurs fichiers."""

import asyncio
import os
import fnmatch
from hypercode.tools.base import Tool, ToolResult


class ReplaceTool(Tool):
    name = "replace"
    description = "Recherche et remplace du texte dans plusieurs fichiers à la fois. Utile pour renommer des variables, changer des imports, etc."
    parameters = {
        "old_text": {
            "type": "string",
            "description": "Texte à rechercher",
            "required": True,
        },
        "new_text": {
            "type": "string",
            "description": "Texte de remplacement",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Répertoire où chercher (défaut: répertoire courant)",
        },
        "pattern": {
            "type": "string",
            "description": "Pattern glob des fichiers (ex: '*.py', '*.js')",
        },
        "dry_run": {
            "type": "boolean",
            "description": "Simuler sans modifier (défaut: false)",
        },
    }

    async def execute(self, old_text: str, new_text: str, path: str = None,
                      pattern: str = None, dry_run: bool = False, **kwargs) -> ToolResult:
        """Remplace du texte dans plusieurs fichiers."""
        search_path = os.path.expanduser(path or os.getcwd())
        skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build", ".next"}

        modified_files = []
        total_replacements = 0

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                if pattern and not fnmatch.fnmatch(filename, pattern):
                    continue

                full_path = os.path.join(root, filename)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    count = content.count(old_text)
                    if count == 0:
                        continue

                    if not dry_run:
                        new_content = content.replace(old_text, new_text)
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(new_content)

                    rel_path = os.path.relpath(full_path, search_path)
                    modified_files.append(f"  {rel_path}: {count} remplacement(s)")
                    total_replacements += count

                except (UnicodeDecodeError, PermissionError):
                    continue

        if not modified_files:
            return ToolResult(success=True, output=f"'{old_text}' non trouvé dans {search_path}")

        prefix = "[DRY RUN] " if dry_run else ""
        output = f"{prefix}{total_replacements} remplacement(s) dans {len(modified_files)} fichier(s):\n" + "\n".join(modified_files)
        return ToolResult(success=True, output=output)
