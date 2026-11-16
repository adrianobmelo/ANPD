from datetime import date

from typer.testing import CliRunner

from estudo import relatorio, revisar
from estudo.cli import app
from helpers import reg

HOJE = date(2026, 11, 16)


def test_relatorio_mostra_amostra_e_marca_insuficiente(con):
    reg(con, 1, "C", "E", tipo="confusao", topico="LGPD.BASES", confundido="LGPD.ANPD")
    reg(con, 2, "C", "B", conf=3)
    txt = relatorio.gerar(con, HOJE)
    for secao in ["SALDO GERAL", "SALDO POR DISCIPLINA", "SALDO POR ASSUNTO", "CURVA DE CONFIANÇA",
                  "TIMIDEZ", "TIPOS DE ERRO", "FALSA CONFIANÇA", "PARES PERIGOSOS",
                  "EVOLUÇÃO POR SEMANA", "DEZ ASSUNTOS PRIORITÁRIOS"]:
        assert secao in txt
    assert "[amostra insuficiente]" in txt
    assert "n=2" in txt
    assert "LGPD.ANPD x LGPD.BASES" in txt or "LGPD.BASES x LGPD.ANPD" in txt
    assert txt.isascii() is False  # acentos, sem emoji
    assert not any(ord(c) > 0x2FFF for c in txt)


def test_barras_em_caracteres():
    assert relatorio.barra_saldo(5, 10) == "..........|#####....."
    assert relatorio.barra_saldo(-10, 10) == "##########|.........."


def test_revisar_traz_motivo(con):
    reg(con, 1, "C", "E", tipo="pressa")
    reg(con, 2, "C", "C", tipo="chute_certo")
    reg(con, 3, "C", "E", tipo="nao_sabia")
    reg(con, 3, "C", "C", data="2026-11-15T10:00:00")  # reacertado: não volta
    itens = revisar.itens_para_revisar(con, HOJE)
    assert [i.referencia for i in itens] == ["1", "2"]
    assert "errou em 2026-11-10 (pressa" in itens[0].motivo
    assert "acertou chutando" in itens[1].motivo
    res = CliRunner().invoke(app, ["revisar"])
    assert res.exit_code == 0 and "pressa" in res.output
