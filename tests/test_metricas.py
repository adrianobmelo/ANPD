from datetime import date

import pytest

from estudo import metricas as m
from helpers import reg

HOJE = date(2026, 11, 16)


@pytest.mark.parametrize("k, n, esperado", [
    (2, 3, 0.208), (10, 20, 0.299), (12, 20, 0.387), (3, 3, 0.438), (5, 5, 0.566),
])
def test_wilson_bate_com_a_tabela_da_fase_0(k, n, esperado):
    assert m.wilson(k, n)[0] == pytest.approx(esperado, abs=0.001)


def test_wilson_sem_amostra():
    assert m.wilson(0, 0) == (0.0, 1.0)


def test_saldo_ignora_brancos_e_chute_certo_conta_ponto(con):
    reg(con, 1, "C", "C")
    reg(con, 2, "C", "E", tipo="nao_sabia")
    reg(con, 3, "C", "B")
    reg(con, 4, "C", "C", tipo="chute_certo")
    s = m.saldo_geral(m.tentativas(con))
    assert (s.total, s.respondidos, s.brancos, s.acertos, s.erros, s.saldo) == (4, 3, 1, 2, 1, 1)
    assert s.taxa_resposta == pytest.approx(0.75)
    assert s.insuficiente


def test_curva_de_confianca_e_ponto_de_corte(con):
    # conf 3: 12 acertos, 0 erros -> compensa. conf 2: 10 acertos, 2 erros -> compensa.
    # conf 1: 5 acertos, 7 erros -> inconclusivo. conf 0: 1 acerto, 11 erros -> branco compensa.
    n = 0
    for conf, acertos, erros in ((3, 12, 0), (2, 10, 2), (1, 5, 7), (0, 1, 11)):
        for _ in range(acertos):
            n += 1; reg(con, n, "C", "C", conf=conf)
        for _ in range(erros):
            n += 1; reg(con, n, "C", "E", conf=conf, tipo="nao_sabia")
    curva = m.curva_confianca(m.tentativas(con))
    assert [c.saldo.saldo for c in curva] == [-10, -2, 8, 12]
    assert [c.veredito for c in curva] == [
        "branco compensa", "inconclusivo (intervalo inclui 50%)",
        "responder compensa", "responder compensa"]
    assert m.ponto_de_corte(curva) == "responder a partir da confiança 2"


def test_curva_com_amostra_pequena_nao_conclui(con):
    reg(con, 1, "C", "C", conf=3)
    curva = m.curva_confianca(m.tentativas(con))
    assert curva[3].veredito == "amostra insuficiente"
    assert "insuficiente" in m.ponto_de_corte(curva)


def test_curva_so_explicita_descarta_padrao_do_turbo(con):
    reg(con, 1, "C", "C", conf=2, explicita="0")
    reg(con, 2, "C", "C", conf=2, explicita="1")
    assert m.curva_confianca(m.tentativas(con))[2].saldo.respondidos == 2
    assert m.curva_confianca(m.tentativas(con), somente_explicita=True)[2].saldo.respondidos == 1


def test_timidez(con):
    reg(con, 1, "C", "B", conf=3)
    reg(con, 2, "C", "B", conf=2)
    reg(con, 3, "C", "B", conf=1)
    assert len(m.timidez(m.tentativas(con))) == 2


def test_ranking_exige_amostra_minima(con):
    # 3 erros em 3: Wilson 0,44, mas fica fora do ranking.
    for i in range(3):
        reg(con, f"b{i}", "C", "E", topico="LGPD.BASES", tipo="nao_sabia")
    # 12 erros em 20 no outro assunto: entra.
    for i in range(20):
        if i < 12:
            reg(con, f"d{i}", "C", "E", tipo="pressa")
        else:
            reg(con, f"d{i}", "C", "C")
    rk, insuf = m.ranking(m.tentativas(con), HOJE)
    assert [p.assunto.topico for p in rk] == [2]
    assert [a.topico for a in insuf] == [3]


def test_prioridade_explica_os_numeros(con):
    reg(con, "x", "C", "E", tipo="nao_sabia", data="2026-11-12T10:00:00")
    reg(con, "x", "C", "E", tipo="nao_sabia", data="2026-11-12T11:00:00")
    for i in range(4):
        reg(con, i, "C", "C")
    rk, _ = m.ranking(m.tentativas(con), HOJE)
    p = rk[0]
    a = p.assunto
    assert a.reincidentes == 1
    assert a.dias_desde_erro(HOJE) == 4
    esperado = m.wilson(2, 6)[0] * 1.1 * (0.5 + 0.5 * 2 ** (-4 / 30))
    assert p.valor == pytest.approx(esperado)
    assert "erro 2/6" in p.porque and "reincidentes 1 (x1.10)" in p.porque
    assert "último erro há 4 dias" in p.porque
    assert "amostra 6, insuficiente" in p.porque


def test_recencia_e_reincidencia_limitadas(con):
    a = m.Assunto(topico=1, reincidentes=50, ultimo_erro="2026-11-16")
    assert a.fator_reincidencia() == pytest.approx(1.5)
    assert a.fator_recencia(HOJE) == pytest.approx(1.0)
    a.ultimo_erro = "2026-10-17"
    assert a.fator_recencia(HOJE) == pytest.approx(0.75)


def test_falsa_confianca_so_com_amostra(con):
    for i in range(4):
        reg(con, i, "C", "C", conf=3)
    for i in range(4, 9):
        reg(con, i, "C", "E", conf=3, tipo="nao_sabia")
    a = m.por_assunto(m.tentativas(con))[2]
    assert a.falsa_confianca is None   # 9 respondidos com conf alta, abaixo de 10
    reg(con, 9, "C", "E", conf=2, tipo="pressa")
    a = m.por_assunto(m.tentativas(con))[2]
    assert a.falsa_confianca is True
    assert a.prioridade(HOJE) == pytest.approx(
        a.wilson_erro[0] * a.fator_reincidencia() * a.fator_recencia(HOJE) * 1.25)


def test_pares_perigosos_sao_simetricos(con):
    reg(con, 1, "C", "E", topico="LGPD.BASES", tipo="confusao", confundido="LGPD.ANPD")
    reg(con, 2, "C", "E", topico="LGPD.ANPD", tipo="confusao", confundido="LGPD.BASES",
        data="2026-11-12T10:00:00")
    reg(con, 3, "C", "C", topico="LGPD.ANPD")
    pares = m.pares(con)
    assert len(pares) == 1
    p = pares[0]
    assert (p["erros_confusao"], p["tentativas_no_par"], p["ultimo_erro"][:10]) == (2, 3, "2026-11-12")
