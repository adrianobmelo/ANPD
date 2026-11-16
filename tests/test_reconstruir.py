from datetime import date

from typer.testing import CliRunner

from estudo import arvores, relatorio
from estudo.cli import app
from estudo.db import caminho_banco, conectar
from estudo.log import Sessao
from estudo.registro import classificar_item
from conftest import Respostas

NOVA = """codigo,nome,disciplina,parent_codigo,aliases
ED.LGPD,LGPD no edital,Direito,,
ED.LGPD.TIT,Titular e direitos,Direito,ED.LGPD,tit
ED.LGPD.BAS,Bases legais,Direito,ED.LGPD,bas
ED.LGPD.AG,ANPD como agência,Direito,ED.LGPD,ag
"""
MAPA = """de_arvore,de_codigo,para_arvore,para_codigo
provisoria,LGPD.DIR,edital,ED.LGPD.TIT
provisoria,LGPD.BASES,edital,ED.LGPD.BAS
provisoria,LGPD.ANPD,edital,ED.LGPD.AG
"""


def test_banco_apagado_e_reconstruido_igual(con, tmp_path):
    s = Sessao(con, Respostas("1", "2", "anpd", "4"), fonte="prova_a")
    for linha in ["1 C E dir", "2 C C 3", "3 E B", "4 C E bases", "5 C C ch", "6 E C"]:
        s.processar(linha)
    Sessao(con, Respostas(), fonte="prova_a").processar("7 C C")  # sessão nova, sem assunto
    item = con.execute("SELECT id FROM items WHERE referencia = '7'").fetchone()[0]
    classificar_item(con, item, con.execute("SELECT id FROM topics WHERE codigo='SI.CRIPTO'").fetchone()[0])

    # edital sai: árvore nova, mapeamento, tentativas antigas preservadas
    (tmp_path / "nova.csv").write_text(NOVA, encoding="utf-8")
    (tmp_path / "mapa.csv").write_text(MAPA, encoding="utf-8")
    arvores.carregar(con, tmp_path / "nova.csv", "edital", ativar=True)
    arvores.mapear(con, tmp_path / "mapa.csv")
    Sessao(con, Respostas(), fonte="prova_b").processar("1 C C tit")

    hoje = date(2026, 11, 16)
    antes = relatorio.gerar(con, hoje)
    assert "ED.LGPD.TIT" in antes and "SI.CRIPTO [provisoria]" in antes
    con.close()

    res = CliRunner().invoke(app, ["reconstruir", "--forcar"])
    assert res.exit_code == 0, res.output
    novo = conectar()
    assert relatorio.gerar(novo, hoje) == antes
    assert novo.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 8
    assert CliRunner().invoke(app, ["auditoria"]).exit_code == 0


def test_reconstruir_nao_apaga_sem_forcar(con):
    res = CliRunner().invoke(app, ["reconstruir"])
    assert res.exit_code == 1
    assert caminho_banco().exists()
