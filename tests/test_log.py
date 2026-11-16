import csv

import pytest

from estudo import log as L
from estudo.registro import TIPOS_ERRO, diario_tentativas


def sessao(con, teclado, *respostas, fonte="cebraspe_2024_anatel"):
    t = teclado(*respostas)
    return L.Sessao(con, t, fonte=fonte), t


def ultima(con):
    return con.execute("SELECT * FROM v_tentativas ORDER BY attempt_id DESC LIMIT 1").fetchone()


def test_item_novo_em_esboco_numa_linha(con, teclado):
    s, t = sessao(con, teclado)
    saida = s.processar("57 C C dir")
    assert "novo, esboço" in saida
    item = con.execute("SELECT * FROM items").fetchone()
    assert (item["fonte"], item["referencia"], item["gabarito"]) == ("cebraspe_2024_anatel", "57", "C")
    assert item["enunciado"] is None
    assert t.prompts == []  # nenhuma pergunta extra para um acerto


def test_registro_rapido_cabe_em_poucas_teclas(con, teclado):
    """Proxy do critério dos vinte segundos: item novo errado = uma linha curta e uma tecla."""
    s, t = sessao(con, teclado, "1")
    linha = "58 C E dir"
    s.processar(linha)
    teclas = len(linha) + 1 + len("1") + 1  # linha + Enter, tipo + Enter
    assert teclas <= 15
    assert len(t.prompts) == 1


def test_confianca_2_assumida_e_marcada(con, teclado):
    s, _ = sessao(con, teclado)
    s.processar("1 C C dir")
    r = ultima(con)
    assert (r["confianca"], r["confianca_explicita"]) == (2, 0)
    s.processar("2 C C 3")
    r = ultima(con)
    assert (r["confianca"], r["confianca_explicita"]) == (3, 1)


def test_assunto_mantido_entre_registros(con, teclado):
    s, _ = sessao(con, teclado)
    s.processar("1 C C bases")
    s.processar("2 E E")
    temas = [r["codigo"] for r in con.execute(
        "SELECT t.codigo FROM items i JOIN topics t ON t.id = i.topic_id ORDER BY i.id")]
    assert temas == ["LGPD.BASES", "LGPD.BASES"]


def test_assunto_por_prefixo_e_por_alias(con, teclado):
    s, _ = sessao(con, teclado)
    s.processar("1 C C SI.CR")       # prefixo de código
    s.processar("2 C C titular")     # alias
    temas = [r["codigo"] for r in con.execute(
        "SELECT t.codigo FROM items i JOIN topics t ON t.id = i.topic_id ORDER BY i.id")]
    assert temas == ["SI.CRIPTO", "LGPD.DIR"]


def test_prefixo_ambiguo_pergunta_e_aceita_numero(con, teclado):
    s, t = sessao(con, teclado, "2")
    s.processar("1 C C LGPD.B")
    assert "ambíguo" in t.prompts[0]
    assert con.execute("SELECT t.codigo FROM items i JOIN topics t ON t.id = i.topic_id").fetchone()[0] \
        == "LGPD.BASES.LI"


def test_sem_assunto_vai_para_fila(con, teclado):
    s, _ = sessao(con, teclado)
    s.processar("1 C C")
    assert con.execute("SELECT topic_id FROM items").fetchone()[0] is None


def test_resposta_aceita_c_e_e_branco(con, teclado):
    s, t = sessao(con, teclado, "4")
    s.processar("1 C c dir")
    s.processar("2 C e")
    s.processar("3 C b")
    s.processar("4 C -")
    assert [r["resposta"] for r in con.execute("SELECT resposta FROM attempts")] == ["C", "E", "B", "B"]


def test_tipo_de_erro_so_perguntado_em_erro_e_sem_valor_preselecionado(con, teclado):
    s, t = sessao(con, teclado, "", "x", "1")
    s.processar("1 C C dir")
    s.processar("2 C B")
    assert t.prompts == []
    s.processar("3 C E")
    # Enter vazio e valor inválido não viram escolha: a pergunta se repete.
    assert len(t.prompts) == 3
    assert ultima(con)["tipo_erro"] == "nao_sabia"
    menu = t.prompts[0]
    assert "chute_certo" not in menu
    assert "[" not in menu and "padrão" not in menu and "default" not in menu.lower()


def test_chute_certo_declarado_por_mim(con, teclado):
    s, t = sessao(con, teclado)
    s.processar("1 C C ch dir")
    assert ultima(con)["tipo_erro"] == "chute_certo"
    assert t.prompts == []
    with pytest.raises(L.LinhaInvalida):
        s.processar("2 C E ch")


def test_confusao_pede_e_grava_o_par(con, teclado):
    s, t = sessao(con, teclado, "2", "anpd")
    s.processar("1 E C bases")
    r = ultima(con)
    assert r["tipo_erro"] == "confusao"
    assert r["topico_confundido"] == con.execute(
        "SELECT id FROM topics WHERE codigo = 'LGPD.ANPD'").fetchone()[0]


def test_item_existente_so_precisa_da_resposta(con, teclado):
    s, t = sessao(con, teclado, "1")
    s.processar("1 C C dir")
    s.processar("1 E")
    assert ultima(con)["gabarito"] == "C" and ultima(con)["acerto"] == 0
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_gabarito_divergente_e_recusado(con, teclado):
    s, _ = sessao(con, teclado)
    s.processar("1 C C dir")
    with pytest.raises(Exception, match="diverge"):
        s.processar("1 E E")
    assert con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_item_novo_com_uma_letra_pergunta_gabarito(con, teclado):
    s, t = sessao(con, teclado, "E")
    s.processar("9 E dir")
    assert "gabarito" in t.prompts[0]
    assert ultima(con)["acerto"] == 1


def test_troca_de_fonte_e_tempo(con, teclado):
    s, _ = sessao(con, teclado, fonte=None)
    with pytest.raises(L.LinhaInvalida):
        s.processar("1 C C")
    s.processar("outra_prova/1 C C 45s")
    r = ultima(con)
    assert r["fonte"] == "outra_prova"
    assert (r["tempo_s"], r["tempo_origem"]) == (45, "cronometro")


def test_cada_registro_vai_para_o_diario(con, teclado):
    s, _ = sessao(con, teclado, "4")
    s.processar("1 C C dir #lembrar do art. 18")
    s.processar("2 C E")
    with open(diario_tentativas(), encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert [l["referencia"] for l in linhas] == ["1", "2"]
    assert linhas[0]["nota"] == "lembrar do art. 18"
    assert linhas[1]["tipo_erro"] == "pressa"


def test_cli_log_ponta_a_ponta(con):
    from typer.testing import CliRunner
    from estudo.cli import app
    res = CliRunner().invoke(app, ["log", "--fonte", "p"], input="1 C E dir\n1\n2 E E\nq\n")
    assert res.exit_code == 0, res.output
    assert "2 itens registrados" in res.output
    for tipo in TIPOS_ERRO:
        # o menu lista as opções, mas nenhuma aparece como sugestão ou padrão
        assert f"[{tipo}]" not in res.output
