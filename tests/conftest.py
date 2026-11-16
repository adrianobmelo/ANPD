import sqlite3
from pathlib import Path

import pytest

from estudo import arvores
from estudo.db import conectar

ARVORE = """codigo,nome,disciplina,parent_codigo,aliases
LGPD,LGPD,Direito,,
LGPD.DIR,Direitos do titular,Direito,LGPD,dir|titular
LGPD.BASES,Bases legais,Direito,LGPD,bases
LGPD.BASES.LI,Legítimo interesse,Direito,LGPD.BASES,li
LGPD.ANPD,ANPD,Direito,LGPD,anpd
SI,Segurança da informação,TI,,
SI.CRIPTO,Criptografia,TI,SI,cripto
"""


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    monkeypatch.setenv("ESTUDO_RAIZ", str(raiz))
    monkeypatch.setenv("ESTUDO_DB", str(tmp_path / "estudo.db"))
    return raiz


@pytest.fixture
def con(ambiente, tmp_path) -> sqlite3.Connection:
    c = conectar()
    csv = tmp_path / "arvore.csv"
    csv.write_text(ARVORE, encoding="utf-8")
    arvores.carregar(c, csv, "provisoria", ativar=True)
    return c


class Respostas:
    """Simula o teclado: devolve as respostas em ordem e guarda os prompts."""

    def __init__(self, *respostas: str):
        self.fila = list(respostas)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.fila:
            raise AssertionError(f"pergunta inesperada: {prompt!r}")
        return self.fila.pop(0)


@pytest.fixture
def teclado():
    return Respostas
