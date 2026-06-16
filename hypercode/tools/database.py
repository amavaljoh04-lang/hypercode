"""Outil de base de données SQL (SQLite, PostgreSQL, MySQL)."""

import asyncio
import os
import sqlite3
from hypercode.tools.base import Tool, ToolResult


class DatabaseTool(Tool):
    name = "database"
    description = "Exécute des requêtes SQL. Supporte SQLite directement. Pour PostgreSQL/MySQL, utilise les outils CLI via bash."
    parameters = {
        "action": {
            "type": "string",
            "description": "'query' pour exécuter une requête, 'schema' pour voir le schéma, 'tables' pour lister les tables",
            "required": True,
            "enum": ["query", "schema", "tables"],
        },
        "database": {
            "type": "string",
            "description": "Chemin du fichier SQLite ou URL de connexion",
            "required": True,
        },
        "sql": {
            "type": "string",
            "description": "Requête SQL à exécuter (pour query)",
        },
        "table": {
            "type": "string",
            "description": "Nom de la table (pour schema)",
        },
    }

    async def execute(self, action: str, database: str, sql: str = None,
                      table: str = None, **kwargs) -> ToolResult:
        """Exécute des opérations SQL."""
        database = os.path.expanduser(database)

        try:
            conn = sqlite3.connect(database)
            cursor = conn.cursor()

            if action == "tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                return ToolResult(success=True, output=f"Tables ({len(tables)}):\n" + "\n".join(f"  - {t}" for t in tables))

            elif action == "schema":
                if table:
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    output = f"Schema de '{table}':\n"
                    for col in columns:
                        output += f"  {col[1]} {col[2]}{'  PRIMARY KEY' if col[5] else ''}{'  NOT NULL' if col[3] else ''}\n"
                else:
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table'")
                    schemas = cursor.fetchall()
                    output = "\n\n".join(s[0] for s in schemas if s[0])
                conn.close()
                return ToolResult(success=True, output=output)

            elif action == "query":
                if not sql:
                    conn.close()
                    return ToolResult(success=False, output="", error="sql requis pour query")

                cursor.execute(sql)

                if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("PRAGMA"):
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []

                    if not rows:
                        conn.close()
                        return ToolResult(success=True, output="Aucun résultat.")

                    # Formater en tableau
                    header = " | ".join(columns)
                    separator = "-+-".join("-" * len(c) for c in columns)
                    output_lines = [header, separator]

                    for row in rows[:100]:
                        output_lines.append(" | ".join(str(v) for v in row))

                    if len(rows) > 100:
                        output_lines.append(f"[...{len(rows)} lignes au total]")

                    conn.close()
                    return ToolResult(success=True, output="\n".join(output_lines))
                else:
                    conn.commit()
                    affected = cursor.rowcount
                    conn.close()
                    return ToolResult(success=True, output=f"{affected} ligne(s) affectée(s)")

            conn.close()
            return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

        except sqlite3.Error as e:
            return ToolResult(success=False, output="", error=f"Erreur SQL: {e}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
