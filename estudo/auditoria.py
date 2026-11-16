"""Auditoria: inconsistências no banco, no diário e nas fontes.

As constraints já impedem a maioria dos problemas na gravação. A auditoria
existe para o que pode surgir depois (gabarito de esboço corrigido, banco
antigo, edição manual) e para o que constraint não cobre (fontes, fila).
"""

from __future__ import annotations

import csv
import sqlite3

from . import fontes
from .fontes import Problema
from .registro import RESPOSTAS, TIPOS_ERRO, diario_tentativas


def _consulta(con, sql) -> list[sqlite3.Row]:
    return con.execute(sql).fetchall()


def auditar(con: sqlite3.Connection) -> list[Problema]:
    ps: list[Problema] = []

    tipos = ",".join(f"'{t}'" for t in TIPOS_ERRO)
    resp = ",".join(f"'{r}'" for r in RESPOSTAS)

    for r in _consulta(con, f"SELECT id, gabarito FROM items WHERE gabarito NOT IN ('C','E')"):
        ps.append(Problema(True, f"item {r['id']}: gabarito inválido '{r['gabarito']}'"))
    for r in _consulta(con, f"SELECT id, resposta FROM attempts WHERE resposta NOT IN ({resp})"):
        ps.append(Problema(True, f"tentativa {r['id']}: resposta inválida '{r['resposta']}'"))
    for r in _consulta(con, "SELECT id FROM attempts WHERE confianca NOT BETWEEN 0 AND 3"
                            " OR typeof(confianca) <> 'integer'"):
        ps.append(Problema(True, f"tentativa {r['id']}: confiança fora de 0 a 3"))
    for r in _consulta(con, f"SELECT id, tipo_erro FROM attempts"
                            f" WHERE tipo_erro IS NOT NULL AND tipo_erro NOT IN ({tipos})"):
        ps.append(Problema(True, f"tentativa {r['id']}: tipo de erro fora da taxonomia '{r['tipo_erro']}'"))

    for r in _consulta(con, """
        SELECT a.id, a.resposta, i.gabarito FROM attempts a JOIN items i ON i.id = a.item_id
        WHERE a.resposta IN ('C','E') AND a.resposta <> i.gabarito
          AND (a.tipo_erro IS NULL OR a.tipo_erro = 'chute_certo')"""):
        ps.append(Problema(True, (
            f"tentativa {r['id']}: errou (respondeu {r['resposta']}, gabarito {r['gabarito']}) "
            "e não tem tipo de erro")))
    for r in _consulta(con, """
        SELECT a.id, a.tipo_erro FROM attempts a JOIN items i ON i.id = a.item_id
        WHERE a.resposta = i.gabarito AND a.tipo_erro IS NOT NULL AND a.tipo_erro <> 'chute_certo'"""):
        ps.append(Problema(True, f"tentativa {r['id']}: acertou mas tem tipo de erro '{r['tipo_erro']}'"))
    for r in _consulta(con, "SELECT id FROM attempts WHERE resposta = 'B' AND tipo_erro IS NOT NULL"):
        ps.append(Problema(True, f"tentativa {r['id']}: branco com tipo de erro"))

    for r in _consulta(con, "SELECT id FROM attempts WHERE tipo_erro = 'confusao'"
                            " AND topic_id_confundido IS NULL"):
        ps.append(Problema(True, f"tentativa {r['id']}: confusão sem assunto confundido"))
    for r in _consulta(con, "SELECT id FROM attempts WHERE COALESCE(tipo_erro,'') <> 'confusao'"
                            " AND topic_id_confundido IS NOT NULL"):
        ps.append(Problema(True, f"tentativa {r['id']}: assunto confundido fora de confusão"))
    for r in _consulta(con, """
        SELECT a.id FROM attempts a JOIN items i ON i.id = a.item_id
        WHERE a.topic_id_confundido = i.topic_id"""):
        ps.append(Problema(False, f"tentativa {r['id']}: confusão com o próprio assunto"))
    for r in _consulta(con, "SELECT id FROM attempts WHERE item_id NOT IN (SELECT id FROM items)"):
        ps.append(Problema(True, f"tentativa {r['id']}: item inexistente"))

    sem_assunto = _consulta(con, "SELECT fonte, referencia FROM items WHERE topic_id IS NULL")
    if sem_assunto:
        exemplos = ", ".join(f"{r['fonte']}/{r['referencia']}" for r in sem_assunto[:5])
        ps.append(Problema(False, (
            f"{len(sem_assunto)} itens sem assunto (rode estudo classificar): {exemplos}"
            + (" ..." if len(sem_assunto) > 5 else ""))))

    # Diário: o banco precisa ser reconstruível a partir dele.
    no_banco = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    diario = diario_tentativas()
    no_diario = 0
    if diario.exists():
        with open(diario, encoding="utf-8", newline="") as f:
            no_diario = sum(1 for _ in csv.DictReader(f))
    if no_banco != no_diario:
        ps.append(Problema(True, (
            f"banco tem {no_banco} tentativas e o diário dados/tentativas.csv tem {no_diario}; "
            "a reconstrução não reproduziria o banco")))

    ps.extend(fontes.verificar())
    return ps
