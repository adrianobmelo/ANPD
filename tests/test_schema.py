import sqlite3

import pytest

INSERT = ("INSERT INTO attempts (item_id, data, resposta, confianca, confianca_explicita,"
          " tipo_erro, topic_id_confundido, tempo_s, tempo_origem) VALUES (?,?,?,?,?,?,?,?,?)")


@pytest.fixture
def base(con):
    con.execute("INSERT INTO items (id, fonte, referencia, gabarito, topic_id, criado_em)"
                " VALUES (1, 'p', '1', 'C', 2, 'x'), (2, 'p', '2', 'E', 3, 'x')")
    return con


def tentar(con, item, resp, conf=2, tipo=None, conf_id=None, tempo=None, origem=None):
    con.execute(INSERT, (item, "2026-11-16", resp, conf, 0, tipo, conf_id, tempo, origem))


@pytest.mark.parametrize("args", [
    (1, "C"), (1, "B"), (1, "C", 2, "chute_certo"), (1, "E", 2, "nao_sabia"),
    (1, "E", 2, "confusao", 3), (1, "E", 2, "pressa", None, 30, "cronometro"),
])
def test_aceita_validos(base, args):
    tentar(base, *args)


@pytest.mark.parametrize("args, motivo", [
    ((1, "X"), "resposta fora de C, E, B"),
    ((1, "B", 2, "pressa"), "branco com tipo"),
    ((1, "C", 2, "pressa"), "acerto com tipo de erro"),
    ((1, "E"), "erro sem tipo"),
    ((1, "E", 2, "chute_certo"), "chute certo em erro"),
    ((1, "E", 2, "confusao"), "confusão sem par"),
    ((1, "E", 2, "pressa", 3), "par fora de confusão"),
    ((1, "E", 2, "outro"), "tipo fora da taxonomia"),
    ((1, "C", 4), "confiança acima de 3"),
    ((1, "C", -1), "confiança abaixo de 0"),
    ((1, "C", 2, None, None, 30), "tempo sem origem"),
    ((99, "C"), "item inexistente"),
])
def test_recusa_invalidos(base, args, motivo):
    with pytest.raises(sqlite3.IntegrityError):
        tentar(base, *args)


def test_gabarito_restrito(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO items (fonte, referencia, gabarito, criado_em) VALUES ('p','1','X','x')")


def test_item_unico_por_fonte_e_referencia(base):
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO items (fonte, referencia, gabarito, criado_em) VALUES ('p','1','E','x')")


def test_acerto_derivado_do_gabarito_e_nulo_em_branco(base):
    tentar(base, 1, "C")
    tentar(base, 1, "E", 2, "nao_sabia")
    tentar(base, 1, "B")
    rows = base.execute("SELECT resposta, acerto, pontos FROM v_tentativas ORDER BY attempt_id").fetchall()
    assert [tuple(r) for r in rows] == [("C", 1, 1), ("E", 0, -1), ("B", None, 0)]


PROIBIDAS = {"acerto", "saldo", "reincidencia", "recencia", "prioridade", "pontos",
             "taxa", "corte", "erro_revisao", "falsa_confianca", "timidez"}


def test_nenhuma_metrica_derivada_persistida(con):
    tabelas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")]
    for t in tabelas:
        for col in con.execute(f"PRAGMA table_info({t})"):
            nome = col["name"]
            assert not any(p in nome for p in PROIBIDAS), f"{t}.{nome} parece métrica derivada"
