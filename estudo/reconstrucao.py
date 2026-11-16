"""Reconstrução do banco a partir de dados/ (árvores, mapas e diários)."""

from __future__ import annotations

import sqlite3

from . import arvores
from . import importar as imp
from .registro import ErroRegistro, diario_classificacoes, diario_tentativas


def banco_vazio(con: sqlite3.Connection) -> bool:
    arv = con.execute("SELECT COUNT(*) FROM topic_trees").fetchone()[0]
    ten = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    return arv == 0 and ten == 0


def ha_diario() -> bool:
    return arvores.eventos_csv().exists() or diario_tentativas().exists()


def reconstruir_em(con: sqlite3.Connection) -> int:
    """Reaplica dados/ num banco vazio. Devolve o número de tentativas."""
    arvores.reaplicar(con)
    if diario_tentativas().exists():
        res = imp.importar(con, diario_tentativas(), dry_run=False, diario=False)
        if res.rejeitadas:
            detalhes = "; ".join(f"linha {n}: {m}" for n, m in res.rejeitadas[:5])
            raise ErroRegistro(f"diário de tentativas com linhas inválidas ({detalhes})")
    if diario_classificacoes().exists():
        imp.importar_classificacoes(con, diario_classificacoes())
    return con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
