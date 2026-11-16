import io

import pytest

from estudo import fontes


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


ITEM = fontes.CATALOGO[0]


def test_baixar_grava_e_registra_hash(ambiente, monkeypatch):
    corpo = b"<html>" + b"x" * 5000 + b"</html>"
    monkeypatch.setattr(fontes.urllib.request, "urlopen", lambda req, timeout: Resp(corpo, ITEM["url"]))
    e = fontes.baixar(ITEM)
    assert (ambiente / "fontes" / ITEM["arquivo"]).read_bytes() == corpo
    assert e["sha256"] == fontes.sha256(ambiente / "fontes" / ITEM["arquivo"])
    assert e["url"] == ITEM["url"]
    assert fontes.verificar() == []


def test_redirecionamento_nao_grava_nada(ambiente, monkeypatch):
    monkeypatch.setattr(fontes.urllib.request, "urlopen",
                        lambda req, timeout: Resp(b"x" * 5000, "https://gov.br/planalto"))
    with pytest.raises(fontes.ErroFonte, match="redirecionou"):
        fontes.baixar(ITEM)
    assert not (ambiente / "fontes" / ITEM["arquivo"]).exists()
