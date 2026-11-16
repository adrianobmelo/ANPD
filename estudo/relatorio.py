"""Relatório em texto, barras em caracteres, amostra em cada linha."""

from __future__ import annotations

import sqlite3
from datetime import date

from . import metricas as m
from . import topicos

LARGURA_BARRA = 20
INSUF = "  [amostra insuficiente]"


def barra_saldo(saldo: int, respondidos: int) -> str:
    """Barra centrada: esquerda negativa, direita positiva, escala pelo respondido."""
    meia = LARGURA_BARRA // 2
    if respondidos == 0:
        return "." * meia + "|" + "." * meia
    tam = round(abs(saldo) / respondidos * meia)
    if saldo < 0:
        return "." * (meia - tam) + "#" * tam + "|" + "." * meia
    return "." * meia + "|" + "#" * tam + "." * (meia - tam)


def _pct(x: float | None) -> str:
    return "  -  " if x is None else f"{x * 100:5.1f}%"


def _linha_saldo(rotulo: str, s: m.Saldo) -> str:
    marca = INSUF if s.insuficiente else ""
    return (
        f"  {rotulo:<28} n={s.total:<4} resp={s.respondidos:<4} br={s.brancos:<4} "
        f"saldo={s.saldo:+4d}  {barra_saldo(s.saldo, s.respondidos)}{marca}"
    )


def gerar(con: sqlite3.Connection, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    ts = m.tentativas(con)
    out: list[str] = []
    p = out.append

    p(f"RELATÓRIO  {hoje.isoformat()}")
    p("Constantes em uso (escolha inicial, não derivadas de dado):")
    for nome, valor in m.CONSTANTES.items():
        p(f"  {nome}: {valor}")
    p("")

    geral = m.saldo_geral(ts)
    p("SALDO GERAL (acertos menos erros, brancos ignorados; chute certo conta como acerto)")
    p(_linha_saldo("geral", geral))
    p(f"  taxa de resposta: {_pct(geral.taxa_resposta)} "
      f"({geral.respondidos} respondidos, {geral.brancos} em branco)")
    p("")

    p("SALDO POR DISCIPLINA")
    disciplinas: dict[str, m.Saldo] = {}
    for t in ts:
        top = topicos.por_id(con, t["topico"])
        chave = top.disciplina if top else "(sem assunto)"
        disciplinas.setdefault(chave, m.Saldo()).somar(t)
    for nome in sorted(disciplinas):
        p(_linha_saldo(nome, disciplinas[nome]))
    p("")

    p("SALDO POR ASSUNTO")
    assuntos = m.por_assunto(ts)
    for topico in sorted(assuntos, key=lambda x: topicos.rotulo(con, x)):
        p(_linha_saldo(topicos.rotulo(con, topico), assuntos[topico].saldo))
    p("")

    for titulo, so_explicita in (
        ("CURVA DE CONFIANÇA (todas as tentativas)", False),
        ("CURVA DE CONFIANÇA (só confiança digitada, sem o padrão do modo turbo)", True),
    ):
        curva = m.curva_confianca(ts, somente_explicita=so_explicita)
        p(titulo)
        p("  Responder compensa quando P(acerto) > 50%, porque o ganho esperado é 2p - 1.")
        for n in curva:
            s = n.saldo
            taxa = s.acertos / s.respondidos if s.respondidos else None
            baixo, alto = n.intervalo
            p(f"  conf {n.nivel}: resp={s.respondidos:<4} acertos={s.acertos:<4} erros={s.erros:<4} "
              f"saldo={s.saldo:+4d}  acerto {_pct(taxa)} [IC {baixo*100:.0f}-{alto*100:.0f}%]  "
              f"{barra_saldo(s.saldo, s.respondidos)}  {n.veredito}")
        p(f"  ponto de corte: {m.ponto_de_corte(curva)}")
        p("")

    tim = m.timidez(ts)
    brancos = geral.brancos
    p(f"TIMIDEZ: {len(tim)} brancos com confiança 2 ou 3, de {brancos} brancos no total")
    if tim:
        contagem: dict[str, int] = {}
        for t in tim:
            r = topicos.rotulo(con, t["topico"])
            contagem[r] = contagem.get(r, 0) + 1
        for r, n in sorted(contagem.items(), key=lambda x: -x[1]):
            p(f"  {r:<28} {n}")
    if brancos < m.MIN_CONCLUSAO:
        p(f"  amostra insuficiente: {brancos} brancos")
    p("")

    tipos = m.tipos_de_erro(ts)
    total_tipos = sum(tipos.values())
    p(f"TIPOS DE ERRO ({total_tipos} tentativas com tipo)")
    for tipo, n in tipos.items():
        tam = round(n / total_tipos * LARGURA_BARRA) if total_tipos else 0
        p(f"  {tipo:<12} {n:>4}  {'#' * tam}")
    if total_tipos < m.MIN_CONCLUSAO:
        p("  amostra insuficiente para comparar tipos")
    p("")

    p("FALSA CONFIANÇA (confiança 2 ou 3 com saldo negativo)")
    algum = False
    for topico, a in sorted(assuntos.items(), key=lambda x: x[1].conf_alta.saldo):
        if a.conf_alta.respondidos == 0:
            continue
        fc = a.falsa_confianca
        if fc is None:
            estado = f"amostra insuficiente ({a.conf_alta.respondidos} de {m.MIN_FALSA_CONFIANCA})"
        else:
            estado = "FALSA CONFIANÇA" if fc else "ok"
        if fc or a.conf_alta.saldo < 0:
            algum = True
            p(f"  {topicos.rotulo(con, topico):<28} resp={a.conf_alta.respondidos:<4} "
              f"saldo={a.conf_alta.saldo:+4d}  {estado}")
    if not algum:
        p("  nenhum assunto com saldo negativo em confiança alta")
    p("")

    p("PARES PERIGOSOS (simétricos)")
    prs = m.pares(con)
    if not prs:
        p("  nenhum erro de confusão registrado")
    for par in prs:
        marca = INSUF if par["tentativas_no_par"] < m.MIN_CONCLUSAO else ""
        p(f"  {topicos.rotulo(con, par['topico_a'])} x {topicos.rotulo(con, par['topico_b'])}: "
          f"{par['erros_confusao']} confusões, {par['tentativas_no_par']} tentativas no par, "
          f"último erro {par['ultimo_erro'][:10]}{marca}")
    p("")

    p("EVOLUÇÃO POR SEMANA (agregado simples, sem janela móvel)")
    for semana, s in m.evolucao_semanal(ts):
        p(_linha_saldo(semana, s))
    p("")

    rk, insuf = m.ranking(ts, hoje)
    p("DEZ ASSUNTOS PRIORITÁRIOS")
    p("  P = Wilson inferior da taxa de erro x fator de reincidência x fator de recência"
      " (x falsa confiança, quando há amostra)")
    if not rk:
        p(f"  nenhum assunto com {m.MIN_RANKING} ou mais itens respondidos")
    for i, pr in enumerate(rk[:10], start=1):
        p(f"  {i:>2}. {topicos.rotulo(con, pr.assunto.topico):<28} P={pr.valor:.2f}  {pr.porque}")
    if insuf:
        p(f"  Fora do ranking por amostra insuficiente (menos de {m.MIN_RANKING} respondidos):")
        for a in insuf:
            p(f"      {topicos.rotulo(con, a.topico):<28} "
              f"{a.erros_revisao} erros em {a.saldo.respondidos} respondidos")
    return "\n".join(out)
