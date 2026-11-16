import csv

from estudo import importar as imp
from estudo.registro import COLUNAS_DIARIO, diario_tentativas


def escrever(caminho, linhas, colunas=None):
    colunas = colunas or ["data", "fonte", "referencia", "gabarito", "topico", "resposta",
                          "confianca", "tipo_erro", "topico_confundido"]
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        w.writerows(linhas)
    return caminho


BOAS = [
    {"data": "2026-11-01", "fonte": "p", "referencia": "1", "gabarito": "C", "topico": "LGPD.DIR",
     "resposta": "C", "confianca": "3"},
    {"data": "2026-11-01", "fonte": "p", "referencia": "2", "gabarito": "E", "topico": "LGPD.BASES",
     "resposta": "C", "confianca": "2", "tipo_erro": "confusao", "topico_confundido": "LGPD.ANPD"},
]


def contar(con):
    return con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]


def test_dry_run_valida_e_nao_grava(con, tmp_path):
    res = imp.importar(con, escrever(tmp_path / "a.csv", BOAS), dry_run=True)
    assert (res.aceitas, res.rejeitadas, res.gravado) == (2, [], False)
    assert contar(con) == 0
    assert not diario_tentativas().exists()


def test_importa_tudo_e_anota_no_diario(con, tmp_path):
    res = imp.importar(con, escrever(tmp_path / "a.csv", BOAS), dry_run=False)
    assert res.gravado and contar(con) == 2
    with open(diario_tentativas(), encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 2


def test_linha_invalida_impede_insercao_parcial(con, tmp_path):
    ruins = BOAS + [
        {"fonte": "p", "referencia": "3", "gabarito": "C", "resposta": "E", "confianca": "2"},
        {"fonte": "p", "referencia": "4", "gabarito": "C", "resposta": "C", "confianca": "7"},
        {"fonte": "p", "referencia": "5", "gabarito": "X", "resposta": "C", "confianca": "1"},
        {"fonte": "p", "referencia": "6", "gabarito": "C", "resposta": "E", "confianca": "1",
         "tipo_erro": "pressa", "topico_confundido": "LGPD.DIR"},
        {"fonte": "p", "referencia": "7", "gabarito": "C", "resposta": "C", "confianca": "1",
         "topico": "NAO.EXISTE"},
    ]
    res = imp.importar(con, escrever(tmp_path / "a.csv", ruins), dry_run=False)
    assert [n for n, _ in res.rejeitadas] == [4, 5, 6, 7, 8]
    assert not res.gravado
    assert contar(con) == 0
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def test_cabecalho_errado(con, tmp_path):
    res = imp.importar(con, escrever(tmp_path / "a.csv", [], ["fonte", "resposta"]), dry_run=False)
    assert res.rejeitadas and "obrigatórias" in res.rejeitadas[0][1]


def test_cli_import_sai_com_erro_quando_rejeita(con, tmp_path):
    from typer.testing import CliRunner
    from estudo.cli import app
    arq = escrever(tmp_path / "a.csv", BOAS + [{"fonte": "p", "referencia": "9", "gabarito": "C",
                                                "resposta": "Z", "confianca": "1"}])
    res = CliRunner().invoke(app, ["import", str(arq)])
    assert res.exit_code == 1
    assert "linha 4" in res.output and "nada foi gravado" in res.output
