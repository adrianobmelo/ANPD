import io
import json

import pytest

from estudo import fontes

ITEM = fontes.CATALOGO[0]
URL = fontes.API_NORMAS.format(urn=ITEM["urn"])


class Resp(io.BytesIO):
    def __init__(self, corpo, url, status=200):
        super().__init__(corpo)
        self.status, self._url = status, url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def corpo(**extra):
    d = {"legislationIdentifier": ITEM["urn"], "headline": "Lei nº 13.709, de 14 de agosto de 2018",
         "dateModified": "2026-02-25", "hasPart": {"workExample": {}},
         "encoding": [{"additionalType": "CompilacaoMonoVigenteNaCD",
                       "legislationLegalValue": "UnofficialLegalValue"}]}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def falso(monkeypatch, conteudo, url=URL):
    monkeypatch.setattr(fontes.urllib.request, "urlopen", lambda req, timeout: Resp(conteudo, url))


def test_baixar_grava_os_bytes_como_vieram_e_registra(ambiente, monkeypatch):
    c = corpo()
    falso(monkeypatch, c)
    e = fontes.baixar(ITEM)
    assert (ambiente / "fontes" / ITEM["arquivo"]).read_bytes() == c
    assert e["sha256"] == fontes.sha256(ambiente / "fontes" / ITEM["arquivo"])
    assert e["url"] == URL and e["urn"] == ITEM["urn"]
    assert e["data_versao"].startswith("2026-02-25 (última alteração")
    assert e["versoes_de_texto_na_fonte"] == ["CompilacaoMonoVigenteNaCD (UnofficialLegalValue)"]
    assert fontes.verificar() == []


@pytest.mark.parametrize("conteudo, url, motivo", [
    (corpo(), "https://normas.leg.br/", "redirecionou"),
    (b"<html>erro</html>", URL, "não devolveu JSON"),
    (corpo(legislationIdentifier="urn:lex:br:federal:lei:2000-01-01;1"), URL, "outra norma"),
    (corpo(hasPart=None), URL, "sem dispositivos"),
])
def test_resposta_suspeita_nao_grava_nada(ambiente, monkeypatch, conteudo, url, motivo):
    falso(monkeypatch, conteudo, url)
    with pytest.raises(fontes.ErroFonte, match=motivo):
        fontes.baixar(ITEM)
    assert not (ambiente / "fontes" / ITEM["arquivo"]).exists()
