"""Conexão, caminhos e migrações. SQL escrito à mão, sem ORM."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PACOTE = Path(__file__).resolve().parent


def raiz() -> Path:
    """Pasta do projeto, onde ficam dados/ e fontes/."""
    return Path(os.environ.get("ESTUDO_RAIZ", Path.cwd())).resolve()


def caminho_banco() -> Path:
    """O banco fica fora do git. ESTUDO_DB manda; senão, pasta de dados do usuário."""
    if "ESTUDO_DB" in os.environ:
        return Path(os.environ["ESTUDO_DB"])
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "estudo" / "estudo.db"


def pasta_dados() -> Path:
    return raiz() / "dados"


def pasta_fontes() -> Path:
    return raiz() / "fontes"


def pasta_migracoes() -> Path:
    for candidata in (PACOTE.parent / "migrations", PACOTE / "_migrations"):
        if candidata.is_dir():
            return candidata
    raise FileNotFoundError("pasta migrations/ não encontrada")


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    caminho = caminho or caminho_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, isolation_level=None)  # transações explícitas
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    migrar(con)
    return con


def migrar(con: sqlite3.Connection) -> list[str]:
    """Aplica, em ordem, os arquivos NNN_*.sql ainda não aplicados."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " versao TEXT PRIMARY KEY, aplicada_em TEXT NOT NULL) STRICT"
    )
    feitas = {r[0] for r in con.execute("SELECT versao FROM schema_migrations")}
    aplicadas = []
    for arq in sorted(pasta_migracoes().glob("[0-9][0-9][0-9]_*.sql")):
        if arq.stem in feitas:
            continue
        sql = arq.read_text(encoding="utf-8")
        con.execute("BEGIN")
        try:
            for comando in _separar(sql):
                con.execute(comando)
            con.execute(
                "INSERT INTO schema_migrations VALUES (?, ?)", (arq.stem, agora())
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        aplicadas.append(arq.stem)
    return aplicadas


def _separar(sql: str) -> list[str]:
    """Divide o script em comandos completos (respeita BEGIN...END de trigger)."""
    comandos, atual = [], ""
    for linha in sql.splitlines(keepends=True):
        atual += linha
        if sqlite3.complete_statement(atual):
            if atual.strip():
                comandos.append(atual)
            atual = ""
    if atual.strip() and not all(
        l.strip().startswith("--") or not l.strip() for l in atual.splitlines()
    ):
        raise ValueError(f"comando SQL incompleto no fim da migração: {atual[:80]}")
    return comandos
