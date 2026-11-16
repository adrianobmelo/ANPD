"""Árvore de assuntos: carga por CSV, busca por prefixo e alias, mapeamento."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import agora

COLUNAS_ARVORE = ["codigo", "nome", "disciplina", "parent_codigo", "aliases"]
COLUNAS_MAPA = ["de_arvore", "de_codigo", "para_arvore", "para_codigo"]


class ErroTopico(Exception):
    pass


@dataclass
class Topico:
    id: int
    codigo: str
    nome: str
    disciplina: str
    arvore: str


def arvore_ativa(con: sqlite3.Connection) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM topic_trees WHERE ativa = 1").fetchone()


def carregar_arvore(
    con: sqlite3.Connection, csv_path: Path, nome: str, ativar: bool
) -> int:
    """Cria uma árvore nova a partir do CSV. Nunca altera árvore existente."""
    with open(csv_path, encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        faltando = set(COLUNAS_ARVORE[:3]) - set(leitor.fieldnames or [])
        if faltando:
            raise ErroTopico(f"CSV de árvore sem colunas: {sorted(faltando)}")
        linhas = list(leitor)
    con.execute("BEGIN")
    try:
        if con.execute("SELECT 1 FROM topic_trees WHERE nome = ?", (nome,)).fetchone():
            raise ErroTopico(f"árvore '{nome}' já existe; árvores não são reescritas")
        if ativar:
            con.execute("UPDATE topic_trees SET ativa = 0 WHERE ativa = 1")
        tree_id = con.execute(
            "INSERT INTO topic_trees (nome, criada_em, ativa) VALUES (?, ?, ?)",
            (nome, agora(), 1 if ativar else 0),
        ).lastrowid
        ids: dict[str, int] = {}
        for n, l in enumerate(linhas, start=2):
            codigo = (l.get("codigo") or "").strip()
            if not codigo or not (l.get("nome") or "").strip():
                raise ErroTopico(f"linha {n}: codigo e nome são obrigatórios")
            ids[codigo] = con.execute(
                "INSERT INTO topics (tree_id, disciplina, codigo, nome) VALUES (?,?,?,?)",
                (tree_id, l["disciplina"].strip(), codigo, l["nome"].strip()),
            ).lastrowid
        for n, l in enumerate(linhas, start=2):
            pai = (l.get("parent_codigo") or "").strip()
            if pai:
                if pai not in ids:
                    raise ErroTopico(f"linha {n}: parent_codigo '{pai}' não existe")
                con.execute(
                    "UPDATE topics SET parent_id = ? WHERE id = ?",
                    (ids[pai], ids[l["codigo"].strip()]),
                )
            for alias in (l.get("aliases") or "").split("|"):
                if alias.strip():
                    con.execute(
                        "INSERT INTO topic_aliases VALUES (?, ?)",
                        (ids[l["codigo"].strip()], alias.strip()),
                    )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return tree_id


def ativar_arvore(con: sqlite3.Connection, nome: str) -> None:
    con.execute("BEGIN")
    try:
        if not con.execute("SELECT 1 FROM topic_trees WHERE nome = ?", (nome,)).fetchone():
            raise ErroTopico(f"árvore '{nome}' não existe")
        con.execute("UPDATE topic_trees SET ativa = 0 WHERE ativa = 1")
        con.execute("UPDATE topic_trees SET ativa = 1 WHERE nome = ?", (nome,))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def carregar_mapa(con: sqlite3.Connection, csv_path: Path) -> int:
    with open(csv_path, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    con.execute("BEGIN")
    try:
        for n, l in enumerate(linhas, start=2):
            de = por_codigo(con, l["de_codigo"], l["de_arvore"])
            para = por_codigo(con, l["para_codigo"], l["para_arvore"])
            if de is None or para is None:
                raise ErroTopico(f"linha {n}: assunto de origem ou destino não existe")
            con.execute(
                "INSERT OR IGNORE INTO topic_map VALUES (?, ?)", (de.id, para.id)
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(linhas)


def _topico(row: sqlite3.Row) -> Topico:
    return Topico(row["id"], row["codigo"], row["nome"], row["disciplina"], row["arvore"])


_SELECT = (
    "SELECT t.id, t.codigo, t.nome, t.disciplina, tt.nome AS arvore "
    "FROM topics t JOIN topic_trees tt ON tt.id = t.tree_id "
)


def por_id(con: sqlite3.Connection, topic_id: int | None) -> Topico | None:
    if topic_id is None:
        return None
    row = con.execute(_SELECT + "WHERE t.id = ?", (topic_id,)).fetchone()
    return _topico(row) if row else None


def por_codigo(con: sqlite3.Connection, codigo: str, arvore: str) -> Topico | None:
    row = con.execute(
        _SELECT + "WHERE t.codigo = ? AND tt.nome = ?", (codigo.strip(), arvore.strip())
    ).fetchone()
    return _topico(row) if row else None


def buscar(con: sqlite3.Connection, termo: str) -> list[Topico]:
    """Busca na árvore ativa: código exato, alias exato, depois prefixo de ambos."""
    termo = termo.strip()
    if not termo:
        return []
    base = _SELECT + "WHERE tt.ativa = 1 AND "
    for cond in (
        "t.codigo = ? COLLATE NOCASE",
        "t.id IN (SELECT topic_id FROM topic_aliases WHERE alias = ?)",
    ):
        rows = con.execute(base + cond, (termo,)).fetchall()
        if rows:
            return [_topico(r) for r in rows]
    prefixo = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = con.execute(
        base
        + "(t.codigo LIKE ? ESCAPE '\\' OR t.id IN (SELECT topic_id FROM topic_aliases"
        " WHERE alias LIKE ? ESCAPE '\\')) ORDER BY t.codigo",
        (prefixo, prefixo),
    ).fetchall()
    return [_topico(r) for r in rows]


def rotulo(con: sqlite3.Connection, topic_id: int | None) -> str:
    t = por_id(con, topic_id)
    if t is None:
        return "(sem assunto)"
    ativa = arvore_ativa(con)
    sufixo = "" if ativa and ativa["nome"] == t.arvore else f" [{t.arvore}]"
    return f"{t.codigo}{sufixo}"
