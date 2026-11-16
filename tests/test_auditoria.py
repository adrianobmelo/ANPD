import json

from typer.testing import CliRunner

from estudo import auditoria, fontes
from estudo.cli import app
from helpers import reg


def mensagens(con):
    return [(p.critico, p.mensagem) for p in auditoria.auditar(con)]


def test_banco_limpo_passa(con):
    reg(con, 1, "C", "C")
    res = CliRunner().invoke(app, ["auditoria"])
    assert res.exit_code == 0, res.output
    assert "0 críticos" in res.output


def test_detecta_inconsistencias_plantadas(con):
    reg(con, 1, "C", "E", tipo="nao_sabia")        # vai virar acerto com tipo
    reg(con, 2, "E", "E")                            # vai virar erro sem tipo
    reg(con, 3, "C", "C", topico="")                 # item sem assunto
    # Gabarito de esboço corrigido depois: as constraints de tentativa não reavaliam.
    con.execute("UPDATE items SET gabarito = 'E' WHERE referencia = '1'")
    con.execute("UPDATE items SET gabarito = 'C' WHERE referencia = '2'")
    # Inconsistências que só entram desligando as constraints (banco antigo ou editado à mão).
    con.execute("PRAGMA ignore_check_constraints = ON")
    con.execute("DROP TRIGGER attempts_tipo_coerente_ins")
    item = con.execute("SELECT id FROM items WHERE referencia = '1'").fetchone()[0]
    ins = ("INSERT INTO attempts (item_id, data, resposta, confianca, confianca_explicita,"
           " tipo_erro, topic_id_confundido) VALUES (?, 'x', ?, ?, 1, ?, ?)")
    con.execute(ins, (item, "X", 2, None, None))            # resposta inválida
    con.execute(ins, (item, "C", 2, "confusao", None))      # confusão sem par
    con.execute(ins, (item, "E", 2, "pressa", 3))           # par fora de confusão
    con.execute(ins, (item, "E", 9, None, None))            # confiança inválida
    con.execute(ins, (item, "B", 2, "pressa", None))        # branco com tipo
    con.execute("INSERT INTO items (fonte, referencia, gabarito, criado_em) VALUES ('p','z','Q','x')")
    con.execute("PRAGMA ignore_check_constraints = OFF")

    msgs = " | ".join(m for _, m in mensagens(con))
    for trecho in ["acertou mas tem tipo de erro", "não tem tipo de erro", "itens sem assunto",
                   "resposta inválida", "confusão sem assunto confundido",
                   "assunto confundido fora de confusão", "confiança fora de 0 a 3",
                   "branco com tipo de erro", "gabarito inválido",
                   "a reconstrução não reproduziria o banco"]:
        assert trecho in msgs, trecho
    res = CliRunner().invoke(app, ["auditoria"])
    assert res.exit_code == 1


def test_fontes_hash_arquivo_fora_e_registro_sem_arquivo(con, ambiente):
    pasta = ambiente / "fontes"
    pasta.mkdir()
    (pasta / "lei_13709_2018.html").write_text("texto original", encoding="utf-8")
    fontes.registrar("lei_13709_2018.html", "LGPD", "Presidência", "https://x", "2026-11-16")
    assert not [p for p in fontes.verificar()]

    (pasta / "lei_13709_2018.html").write_text("texto alterado", encoding="utf-8")
    (pasta / "lei_99999_2030.html").write_text("solto", encoding="utf-8")
    idx = json.loads((pasta / "index.json").read_text(encoding="utf-8"))
    idx.append({**idx[0], "arquivo": "lei_14133_2021.html"})
    (pasta / "index.json").write_text(json.dumps(idx), encoding="utf-8")

    msgs = [p.mensagem for p in fontes.verificar() if p.critico]
    assert any("hash divergente em lei_13709_2018.html" in m for m in msgs)
    assert any("fora do índice: lei_99999_2030.html" in m for m in msgs)
    assert any("sem arquivo: lei_14133_2021.html" in m for m in msgs)
    assert (pasta / "lei_13709_2018.html").exists()  # nada é apagado
    assert CliRunner().invoke(app, ["auditoria"]).exit_code == 1


def test_nome_de_fonte_fora_do_padrao(ambiente):
    import pytest
    (ambiente / "fontes").mkdir()
    (ambiente / "fontes" / "LGPD.pdf").write_bytes(b"x")
    with pytest.raises(fontes.ErroFonte):
        fontes.registrar("LGPD.pdf", "LGPD", "x", "x", "x")
