"""Leitura da LGPD a partir das fontes reais do repositório."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from estudo import leitura
from estudo.cli import app

FONTES = Path(__file__).resolve().parents[1] / "fontes"
LGPD = FONTES / "lei_13709_2018.json"
L15352 = FONTES / "lei_15352_2026.json"

pytestmark = pytest.mark.skipif(not LGPD.exists(), reason="fontes não baixadas")


def textos_da_fonte(caminho):
    """Todos os textos e rótulos de todas as versões, como estão no arquivo."""
    achados = set()

    def visitar(o):
        if isinstance(o, dict):
            for chave in ("text", "name"):
                if isinstance(o.get(chave), str):
                    achados.add(leitura.limpar(o[chave]))
            for v in o.values():
                visitar(v)
        elif isinstance(o, list):
            for x in o:
                visitar(x)

    visitar(json.loads(caminho.read_text(encoding="utf-8")))
    return achados


def test_todo_texto_de_leitura_existe_literalmente_na_fonte():
    fonte = textos_da_fonte(LGPD)
    ds = leitura.dispositivos(LGPD)
    assert len(ds) > 500
    for d in ds:
        if d.texto:
            assert d.texto in fonte, d.id
        if d.rotulo:
            assert leitura.limpar(d.rotulo) in fonte, d.id


def test_texto_vigente_traz_a_agencia_e_nao_o_suprimido():
    ds = {d.id: d for d in leitura.dispositivos(LGPD)}
    assert "Agência Nacional de Proteção de Dados" in ds["art55-1_cpt"].texto
    assert ds["art55-1_cpt"].redacao_de.startswith("Lei nº 15.352")
    assert not any(d.texto.endswith("(Suprimido)") for d in ds.values())


def test_incisos_acrescidos_ficam_na_ordem():
    ids = [d.id for d in leitura.dispositivos(LGPD) if d.id.startswith("art55-3_cpt_inc")]
    assert ids == ["art55-3_cpt_inc1", "art55-3_cpt_inc2", "art55-3_cpt_inc3", "art55-3_cpt_inc4",
                   "art55-3_cpt_inc5", "art55-3_cpt_inc5-1", "art55-3_cpt_inc5-2", "art55-3_cpt_inc6"]


def test_confronto_acha_a_secao_que_a_consolidacao_nao_atualizou():
    conf = leitura.confrontar(leitura.dispositivos(LGPD), leitura.dispositivos(L15352), "art1_cpt_alt1_")
    situacao = {c.id: c.situacao for c in conf}
    assert situacao["cap9_sec1"].startswith("DIVERGE")
    assert "Da Agência Nacional de Proteção de Dados" in next(
        c.texto_alteradora for c in conf if c.id == "cap9_sec1")
    assert all(s.startswith("consolidação igual") for i, s in situacao.items() if i != "cap9_sec1")


def test_comando_leitura_gera_o_arquivo(ambiente):
    shutil.copytree(FONTES, ambiente / "fontes")
    res = CliRunner().invoke(app, ["leitura", "lgpd"])
    assert res.exit_code == 0, res.output
    md = (ambiente / "leitura" / "lgpd.md").read_text(encoding="utf-8")
    assert "Desatualizado na consolidação" in md
    assert "**[Lei 15.352]**" in md
    repo = FONTES.parent / "leitura" / "lgpd.md"
    if repo.exists():
        assert md == repo.read_text(encoding="utf-8"), "leitura/lgpd.md do repositório está velho"


def test_leitura_recusa_fonte_alterada(ambiente):
    shutil.copytree(FONTES, ambiente / "fontes")
    with open(ambiente / "fontes" / "lei_13709_2018.json", "a", encoding="utf-8") as f:
        f.write(" ")
    res = CliRunner().invoke(app, ["leitura", "lgpd"])
    assert res.exit_code == 1 and "hash divergente" in res.output
