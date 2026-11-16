"""Árvores de assuntos no diário (dados/) e sumário extraído das fontes.

dados/arvores/<nome>.csv guarda cada árvore carregada; dados/arvores.csv guarda
os eventos (carregar, ativar) na ordem; dados/mapas.csv guarda os mapeamentos.
Com isso a reconstrução refaz a mesma sequência.
"""

from __future__ import annotations

import csv
import re
import shutil
import sqlite3
from html.parser import HTMLParser
from pathlib import Path

from . import topicos
from .db import agora, pasta_dados
from .registro import anexar_csv

COLUNAS_EVENTOS = ["data", "acao", "nome"]


def eventos_csv() -> Path:
    return pasta_dados() / "arvores.csv"


def mapas_csv() -> Path:
    return pasta_dados() / "mapas.csv"


def arquivo_arvore(nome: str) -> Path:
    return pasta_dados() / "arvores" / f"{nome}.csv"


def carregar(con: sqlite3.Connection, origem: Path, nome: str, ativar: bool) -> int:
    if not re.fullmatch(r"[a-z0-9_]+", nome):
        raise topicos.ErroTopico("nome da árvore: só minúsculas, dígitos e _")
    destino = arquivo_arvore(nome)
    if destino.exists() and destino.resolve() != origem.resolve():
        raise topicos.ErroTopico(f"já existe {destino}; árvores não são reescritas")
    tree_id = topicos.carregar_arvore(con, origem, nome, ativar)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.resolve() != origem.resolve():
        shutil.copyfile(origem, destino)
    eventos = [{"data": agora(), "acao": "carregar", "nome": nome}]
    if ativar:
        eventos.append({"data": agora(), "acao": "ativar", "nome": nome})
    anexar_csv(eventos_csv(), COLUNAS_EVENTOS, eventos)
    return tree_id


def ativar(con: sqlite3.Connection, nome: str) -> None:
    topicos.ativar_arvore(con, nome)
    anexar_csv(eventos_csv(), COLUNAS_EVENTOS, [{"data": agora(), "acao": "ativar", "nome": nome}])


def mapear(con: sqlite3.Connection, origem: Path) -> int:
    n = topicos.carregar_mapa(con, origem)
    with open(origem, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    anexar_csv(mapas_csv(), topicos.COLUNAS_MAPA, linhas)
    return n


def reaplicar(con: sqlite3.Connection) -> None:
    """Refaz árvores e mapas a partir do diário, sem gravar nele de novo."""
    if eventos_csv().exists():
        with open(eventos_csv(), encoding="utf-8", newline="") as f:
            for e in csv.DictReader(f):
                if e["acao"] == "carregar":
                    topicos.carregar_arvore(con, arquivo_arvore(e["nome"]), e["nome"], False)
                elif e["acao"] == "ativar":
                    topicos.ativar_arvore(con, e["nome"])
    if mapas_csv().exists():
        topicos.carregar_mapa(con, mapas_csv())


# ------------------------------------------------------------------ sumário

ROMANO = r"[IVXLC]+"
CABECALHO = re.compile(
    rf"^(T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|Se[çc][ãa]o|LIVRO)\s+({ROMANO}|[ÚU]NIC[OA])\b",
)
NIVEL = {"LIVRO": 0, "TITULO": 1, "CAPITULO": 2, "SECAO": 3}


class _Texto(HTMLParser):
    BLOCOS = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        if tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar -= 1
        if tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def _sem_acento(s: str) -> str:
    return (s.upper().replace("Í", "I").replace("Ç", "C").replace("Ã", "A")
            .replace("Ú", "U"))


def linhas_texto(caminho: Path) -> list[str]:
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    p = _Texto()
    p.feed(texto)
    linhas = []
    for l in "".join(p.partes).splitlines():
        l = " ".join(l.split())
        if l:
            linhas.append(l)
    return linhas


def sumario(caminho: Path, prefixo: str, disciplina: str, nome_raiz: str) -> list[dict]:
    """Títulos, capítulos e seções do arquivo, na ordem, como linhas de árvore.

    O nome do assunto é o texto literal do cabeçalho e da linha seguinte no
    arquivo; nada é escrito de memória. Trechos riscados (texto revogado em
    <strike>) não são tratados aqui: revise o CSV antes de carregar.
    """
    linhas = linhas_texto(caminho)
    saida: list[dict] = [{"codigo": prefixo, "nome": nome_raiz, "disciplina": disciplina,
                          "parent_codigo": "", "aliases": ""}]
    pilha: list[tuple[int, str]] = []
    contagem: dict[str, int] = {}
    for i, l in enumerate(linhas):
        m = CABECALHO.match(l)
        if not m:
            continue
        tipo = _sem_acento(m.group(1))
        nivel = NIVEL[tipo]
        resto = l[m.end():].strip(" -–")
        if not resto and i + 1 < len(linhas) and not CABECALHO.match(linhas[i + 1]) \
                and not linhas[i + 1].startswith("Art"):
            resto = linhas[i + 1]
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        pai = pilha[-1][1] if pilha else prefixo
        sigla = {"LIVRO": "L", "TITULO": "T", "CAPITULO": "C", "SECAO": "S"}[tipo]
        base = f"{pai}.{sigla}{m.group(2).upper()}"
        contagem[base] = contagem.get(base, 0) + 1
        codigo = base if contagem[base] == 1 else f"{base}_{contagem[base]}"
        nome = f"{m.group(1)} {m.group(2)}" + (f" - {resto}" if resto else "")
        saida.append({"codigo": codigo, "nome": nome, "disciplina": disciplina,
                      "parent_codigo": pai, "aliases": ""})
        pilha.append((nivel, codigo))
    return saida


def gravar_sumario(linhas: list[dict], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=topicos.COLUNAS_ARVORE)
        w.writeheader()
        w.writerows(linhas)
