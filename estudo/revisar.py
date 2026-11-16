"""O que volta hoje, com o motivo. Sem motor de repetição espaçada (regra 3).

Fase 1: volta o item cuja última tentativa foi erro ou chute certo, ou seja,
que ainda não teve acerto limpo depois do erro. Ordem pela prioridade do assunto.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from . import metricas as m
from . import topicos


@dataclass
class Revisao:
    fonte: str
    referencia: str
    topico: int | None
    prioridade: float | None
    motivo: str


def itens_para_revisar(con: sqlite3.Connection, hoje: date, limite: int = 20) -> list[Revisao]:
    ts = m.tentativas(con)
    rk, _ = m.ranking(ts, hoje)
    prioridade = {p.assunto.topico: p.valor for p in rk}
    ultima: dict[int, sqlite3.Row] = {}
    for t in ts:  # ts já vem em ordem cronológica
        ultima[t["item_id"]] = t
    revisoes = []
    for t in ultima.values():
        if t["erro_revisao"] != 1:
            continue
        if t["tipo_erro"] == "chute_certo":
            motivo = f"acertou chutando em {t['data'][:10]}"
        else:
            motivo = f"errou em {t['data'][:10]} ({t['tipo_erro']}"
            if t["tipo_erro"] == "confusao":
                motivo += f" com {topicos.rotulo(con, t['topico_confundido'])}"
            motivo += f", confiança {t['confianca']})"
        p = prioridade.get(t["topico"])
        motivo += "; assunto " + (f"P={p:.2f}" if p is not None else "fora do ranking")
        revisoes.append(Revisao(t["fonte"], t["referencia"], t["topico"], p, motivo))
    revisoes.sort(key=lambda r: (r.prioridade is None, -(r.prioridade or 0)))
    return revisoes[:limite]
