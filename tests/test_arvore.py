import pytest

from estudo import arvores, metricas, topicos
from helpers import reg
from test_reconstruir import MAPA, NOVA


def test_arvore_nova_preserva_tentativas_pelo_mapeamento(con, tmp_path):
    reg(con, 1, "C", "E", tipo="nao_sabia")
    original = con.execute("SELECT topic_id FROM items").fetchone()[0]
    (tmp_path / "n.csv").write_text(NOVA, encoding="utf-8")
    (tmp_path / "m.csv").write_text(MAPA, encoding="utf-8")
    arvores.carregar(con, tmp_path / "n.csv", "edital", ativar=True)
    arvores.mapear(con, tmp_path / "m.csv")
    assert con.execute("SELECT topic_id FROM items").fetchone()[0] == original  # nada reescrito
    t = metricas.tentativas(con)[0]
    assert topicos.rotulo(con, t["topico"]) == "ED.LGPD.TIT"


def test_arvore_existente_nao_e_reescrita(con, tmp_path):
    (tmp_path / "n.csv").write_text(NOVA, encoding="utf-8")
    with pytest.raises(topicos.ErroTopico):
        arvores.carregar(con, tmp_path / "n.csv", "provisoria", ativar=False)


def test_so_uma_arvore_ativa(con, tmp_path):
    (tmp_path / "n.csv").write_text(NOVA, encoding="utf-8")
    arvores.carregar(con, tmp_path / "n.csv", "edital", ativar=True)
    assert con.execute("SELECT COUNT(*) FROM topic_trees WHERE ativa = 1").fetchone()[0] == 1
    assert topicos.buscar(con, "dir") == []          # árvore antiga não entra na busca
    assert topicos.buscar(con, "tit")[0].codigo == "ED.LGPD.TIT"


HTML = """<html><body>
<p>LEI Nº 13.709, DE 14 DE AGOSTO DE 2018</p>
<p>CAPÍTULO I</p><p>DISPOSIÇÕES PRELIMINARES</p>
<p>Art. 1º Esta Lei dispõe...</p>
<p>CAPÍTULO II</p><p>DO TRATAMENTO DE DADOS PESSOAIS</p>
<p>Seção I</p><p>Dos Requisitos para o Tratamento de Dados Pessoais</p>
<p>Art. 7º O tratamento...</p>
<p>Seção II</p><p>Do Tratamento de Dados Pessoais Sensíveis</p>
<p>CAPÍTULO III</p><p>DOS DIREITOS DO TITULAR</p>
</body></html>"""


def test_sumario_usa_so_o_texto_do_arquivo(tmp_path):
    arq = tmp_path / "lei.html"
    arq.write_text(HTML, encoding="utf-8")
    linhas = arvores.sumario(arq, "LGPD", "Direito", "LGPD")
    assert [(l["codigo"], l["parent_codigo"]) for l in linhas] == [
        ("LGPD", ""), ("LGPD.CI", "LGPD"), ("LGPD.CII", "LGPD"),
        ("LGPD.CII.SI", "LGPD.CII"), ("LGPD.CII.SII", "LGPD.CII"), ("LGPD.CIII", "LGPD")]
    texto = arq.read_text(encoding="utf-8")
    for l in linhas[1:]:
        cabecalho, _, resto = l["nome"].partition(" - ")
        assert cabecalho in texto and resto in texto
