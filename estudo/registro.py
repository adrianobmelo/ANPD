"""Registro de tentativa: regra única usada por log, import e reconstrução.

Toda tentativa gravada no banco também vai para o diário dados/tentativas.csv,
que fica no git. O banco é descartável; o diário é a fonte da reconstrução.
"""

from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import topicos
from .db import agora, pasta_dados

TIPOS_ERRO = ("nao_sabia", "confusao", "enunciado", "pressa", "chute_certo")
TIPOS_ERRO_DE_ERRO = ("nao_sabia", "confusao", "enunciado", "pressa")
RESPOSTAS = ("C", "E", "B")
ORIGENS_TEMPO = ("cli_intervalo", "cronometro", "estimado")


class ErroRegistro(Exception):
    pass


@dataclass
class Registro:
    data: str
    fonte: str
    referencia: str
    gabarito: str
    arvore: str
    topico: str
    resposta: str
    confianca: str
    confianca_explicita: str
    tempo_s: str = ""
    tempo_origem: str = ""
    tipo_erro: str = ""
    arvore_confundido: str = ""
    topico_confundido: str = ""
    nota: str = ""
    ano: str = ""
    orgao: str = ""
    cargo: str = ""


COLUNAS_DIARIO = [f.name for f in fields(Registro)]
COLUNAS_CLASSIFICACAO = ["data", "fonte", "referencia", "arvore", "topico"]


def diario_tentativas() -> Path:
    return pasta_dados() / "tentativas.csv"


def diario_classificacoes() -> Path:
    return pasta_dados() / "classificacoes.csv"


def anexar_csv(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists() or caminho.stat().st_size == 0
    with open(caminho, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        if novo:
            w.writeheader()
        for l in linhas:
            w.writerow({c: l.get(c, "") for c in colunas})
        f.flush()
        os.fsync(f.fileno())


def _int_ou_none(valor: str, campo: str) -> int | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        raise ErroRegistro(f"{campo} precisa ser inteiro, veio '{valor}'")


def _topico(con, arvore: str, codigo: str, campo: str) -> int | None:
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    if not arvore:
        ativa = topicos.arvore_ativa(con)
        if ativa is None:
            raise ErroRegistro(f"{campo}: não há árvore ativa para resolver '{codigo}'")
        arvore = ativa["nome"]
    t = topicos.por_codigo(con, codigo, arvore)
    if t is None:
        raise ErroRegistro(f"{campo}: assunto '{codigo}' não existe na árvore '{arvore}'")
    return t.id


def aplicar(con: sqlite3.Connection, r: Registro) -> int:
    """Grava item (se novo) e tentativa. Não abre nem fecha transação.

    Lança ErroRegistro ou sqlite3.IntegrityError; nenhuma constraint é contornada.
    """
    fonte, ref = r.fonte.strip(), r.referencia.strip()
    if not fonte or not ref:
        raise ErroRegistro("fonte e referencia são obrigatórias")
    gabarito = r.gabarito.strip().upper()
    resposta = r.resposta.strip().upper()
    if resposta not in RESPOSTAS:
        raise ErroRegistro(f"resposta precisa ser C, E ou B, veio '{r.resposta}'")
    if gabarito and gabarito not in ("C", "E"):
        raise ErroRegistro(f"gabarito precisa ser C ou E, veio '{r.gabarito}'")
    tipo = r.tipo_erro.strip() or None
    if tipo is not None and tipo not in TIPOS_ERRO:
        raise ErroRegistro(f"tipo_erro fora da taxonomia: '{tipo}'")
    origem = r.tempo_origem.strip() or None
    topic_id = _topico(con, r.arvore.strip(), r.topico, "topico")
    confundido = _topico(con, r.arvore_confundido.strip(), r.topico_confundido, "topico_confundido")

    item = con.execute(
        "SELECT id, gabarito, topic_id FROM items WHERE fonte = ? AND referencia = ?",
        (fonte, ref),
    ).fetchone()
    if item is None:
        if not gabarito:
            raise ErroRegistro(f"item {fonte}/{ref} não existe; informe o gabarito para criar o esboço")
        item_id = con.execute(
            "INSERT INTO items (fonte, referencia, ano, orgao, cargo, gabarito, topic_id, criado_em)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fonte, ref, _int_ou_none(r.ano, "ano"), r.orgao.strip() or None,
             r.cargo.strip() or None, gabarito, topic_id, r.data or agora()),
        ).lastrowid
    else:
        item_id = item["id"]
        if gabarito and gabarito != item["gabarito"]:
            raise ErroRegistro(
                f"gabarito informado ({gabarito}) diverge do item {fonte}/{ref} ({item['gabarito']})"
            )
        if topic_id is not None:
            if item["topic_id"] is None:
                con.execute("UPDATE items SET topic_id = ? WHERE id = ?", (topic_id, item_id))
            elif item["topic_id"] != topic_id:
                raise ErroRegistro(f"item {fonte}/{ref} já está classificado em outro assunto")

    confianca = _int_ou_none(r.confianca, "confianca")
    if confianca is None:
        raise ErroRegistro("confianca é obrigatória")
    explicita = _int_ou_none(r.confianca_explicita, "confianca_explicita")
    return con.execute(
        "INSERT INTO attempts (item_id, data, resposta, confianca, confianca_explicita,"
        " tempo_s, tempo_origem, tipo_erro, topic_id_confundido, nota)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, r.data or agora(), resposta, confianca,
         1 if explicita is None else explicita,
         _int_ou_none(r.tempo_s, "tempo_s"), origem, tipo, confundido,
         r.nota.strip() or None),
    ).lastrowid


def registrar(con: sqlite3.Connection, r: Registro, diario: bool = True) -> int:
    """Uma tentativa, em transação, com linha no diário antes do commit."""
    con.execute("BEGIN")
    try:
        attempt_id = aplicar(con, r)
        if diario:
            anexar_csv(diario_tentativas(), COLUNAS_DIARIO, [asdict(r)])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return attempt_id


def classificar_item(
    con: sqlite3.Connection, item_id: int, topic_id: int, diario: bool = True
) -> None:
    item = con.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    t = topicos.por_id(con, topic_id)
    if item is None or t is None:
        raise ErroRegistro("item ou assunto inexistente")
    if item["topic_id"] is not None:
        raise ErroRegistro("item já classificado")
    con.execute("BEGIN")
    try:
        con.execute("UPDATE items SET topic_id = ? WHERE id = ?", (topic_id, item_id))
        if diario:
            anexar_csv(diario_classificacoes(), COLUNAS_CLASSIFICACAO, [{
                "data": agora(), "fonte": item["fonte"], "referencia": item["referencia"],
                "arvore": t.arvore, "topico": t.codigo,
            }])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
