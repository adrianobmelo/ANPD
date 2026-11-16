"""Importação de tentativas por CSV: tudo ou nada, com dry-run e relatório."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .registro import (
    COLUNAS_DIARIO, ErroRegistro, Registro, aplicar, anexar_csv, diario_tentativas,
)
from . import topicos

OBRIGATORIAS = {"fonte", "referencia", "resposta", "confianca"}


@dataclass
class Resultado:
    lidas: int = 0
    aceitas: int = 0
    rejeitadas: list[tuple[int, str]] = field(default_factory=list)
    gravado: bool = False


def ler(caminho: Path) -> tuple[list[str], list[dict]]:
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        return list(leitor.fieldnames or []), list(leitor)


def importar(
    con: sqlite3.Connection, caminho: Path, dry_run: bool, diario: bool = True
) -> Resultado:
    colunas, linhas = ler(caminho)
    res = Resultado(lidas=len(linhas))
    faltando = OBRIGATORIAS - set(colunas)
    if faltando:
        res.rejeitadas.append((1, f"cabeçalho sem colunas obrigatórias: {sorted(faltando)}"))
        return res
    desconhecidas = set(colunas) - set(COLUNAS_DIARIO)
    if desconhecidas:
        res.rejeitadas.append((1, f"colunas desconhecidas: {sorted(desconhecidas)}"))
        return res

    registros = []
    con.execute("BEGIN")
    try:
        for n, linha in enumerate(linhas, start=2):
            dados = {c: (linha.get(c) or "") for c in COLUNAS_DIARIO}
            if not dados["confianca_explicita"]:
                dados["confianca_explicita"] = "1"
            # Fixa a árvore usada na resolução, para a reconstrução não depender
            # de qual árvore estará ativa no futuro.
            ativa = topicos.arvore_ativa(con)
            if ativa is not None:
                if dados["topico"] and not dados["arvore"]:
                    dados["arvore"] = ativa["nome"]
                if dados["topico_confundido"] and not dados["arvore_confundido"]:
                    dados["arvore_confundido"] = ativa["nome"]
            r = Registro(**dados)
            con.execute("SAVEPOINT linha")
            try:
                aplicar(con, r)
                con.execute("RELEASE linha")
                registros.append(r)
                res.aceitas += 1
            except (ErroRegistro, sqlite3.IntegrityError) as e:
                con.execute("ROLLBACK TO linha")
                con.execute("RELEASE linha")
                res.rejeitadas.append((n, str(e)))
        if dry_run or res.rejeitadas:
            con.execute("ROLLBACK")
            return res
        if diario:
            anexar_csv(diario_tentativas(), COLUNAS_DIARIO, [asdict(r) for r in registros])
        con.execute("COMMIT")
        res.gravado = True
        return res
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def importar_classificacoes(con: sqlite3.Connection, caminho: Path) -> int:
    """Reaplica o diário de classificações (usado na reconstrução)."""
    _, linhas = ler(caminho)
    con.execute("BEGIN")
    try:
        for n, l in enumerate(linhas, start=2):
            t = topicos.por_codigo(con, l["topico"], l["arvore"])
            item = con.execute(
                "SELECT id, topic_id FROM items WHERE fonte = ? AND referencia = ?",
                (l["fonte"], l["referencia"]),
            ).fetchone()
            if t is None or item is None:
                raise ErroRegistro(f"classificacoes.csv linha {n}: item ou assunto inexistente")
            if item["topic_id"] is None:
                con.execute("UPDATE items SET topic_id = ? WHERE id = ?", (t.id, item["id"]))
            elif item["topic_id"] != t.id:
                raise ErroRegistro(f"classificacoes.csv linha {n}: item já em outro assunto")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(linhas)
