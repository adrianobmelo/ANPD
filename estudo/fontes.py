"""Fontes oficiais em fontes/ e o índice fontes/index.json com hash.

Regra 1: nenhum conteúdo jurídico vem de memória de modelo. O que não está
aqui, com hash conferido, não existe para o sistema.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .db import pasta_fontes

NOME_VALIDO = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*\.(html|htm|pdf|txt)$")

# Catálogo do núcleo inicial. URLs oficiais do Planalto.
CATALOGO = [
    {
        "arquivo": "lei_13709_2018.html",
        "norma": "Lei 13.709/2018 (LGPD), texto compilado",
        "orgao": "Presidência da República",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm",
    },
    {
        "arquivo": "lei_15352_2026.html",
        "norma": "Lei 15.352/2026",
        "orgao": "Presidência da República",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/L15352.htm",
    },
    {
        "arquivo": "lei_14133_2021.html",
        "norma": "Lei 14.133/2021 (licitações e contratos)",
        "orgao": "Presidência da República",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm",
    },
]


class ErroFonte(Exception):
    pass


def caminho_index() -> Path:
    return pasta_fontes() / "index.json"


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def ler_index() -> list[dict]:
    p = caminho_index()
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def gravar_index(entradas: list[dict]) -> None:
    p = caminho_index()
    p.parent.mkdir(parents=True, exist_ok=True)
    entradas = sorted(entradas, key=lambda e: e["arquivo"])
    p.write_text(json.dumps(entradas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def registrar(arquivo: str, norma: str, orgao: str, url: str, data_versao: str) -> dict:
    """Registra no índice um arquivo que já está em fontes/."""
    if not NOME_VALIDO.match(arquivo):
        raise ErroFonte(f"nome fora do padrão (minúsculo, identificador e ano): {arquivo}")
    caminho = pasta_fontes() / arquivo
    if not caminho.exists():
        raise ErroFonte(f"arquivo não encontrado em fontes/: {arquivo}")
    entrada = {
        "arquivo": arquivo, "norma": norma, "orgao": orgao, "url": url,
        "data_versao": data_versao, "sha256": sha256(caminho),
    }
    entradas = [e for e in ler_index() if e["arquivo"] != arquivo] + [entrada]
    gravar_index(entradas)
    return entrada


def baixar(item: dict, timeout: int = 60) -> dict:
    """Baixa da URL oficial, grava em fontes/ e registra. data_versao = data do download,
    porque a página compilada do Planalto não traz data de versão própria."""
    destino = pasta_fontes() / item["arquivo"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(item["url"], headers={"User-Agent": "estudo-anpd/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ErroFonte(f"{item['url']} respondeu {resp.status}")
        final = resp.geturl()
        conteudo = resp.read()
    if final.rstrip("/") != item["url"].rstrip("/"):
        raise ErroFonte(f"{item['url']} redirecionou para {final}; nada foi gravado")
    if len(conteudo) < 1000:
        raise ErroFonte(f"{item['url']} devolveu só {len(conteudo)} bytes; nada foi gravado")
    destino.write_bytes(conteudo)
    return registrar(item["arquivo"], item["norma"], item["orgao"], item["url"],
                     f"obtido em {date.today().isoformat()}")


@dataclass
class Problema:
    critico: bool
    mensagem: str


def verificar() -> list[Problema]:
    """Hash divergente, arquivo fora do índice, registro sem arquivo."""
    problemas = []
    pasta = pasta_fontes()
    entradas = ler_index()
    no_index = {e["arquivo"] for e in entradas}
    for e in entradas:
        caminho = pasta / e["arquivo"]
        if not caminho.exists():
            problemas.append(Problema(True, f"fonte no índice sem arquivo: {e['arquivo']}"))
        elif sha256(caminho) != e["sha256"]:
            problemas.append(Problema(True, (
                f"hash divergente em {e['arquivo']}: o arquivo mudou desde o registro. "
                "Cartões que citam esta fonte podem estar desatualizados (cartões são da Fase 2); "
                "nada foi apagado")))
    if pasta.exists():
        for arq in sorted(pasta.iterdir()):
            if arq.is_file() and arq.name != "index.json" and not arq.name.startswith("."):
                if arq.name not in no_index:
                    problemas.append(Problema(True, f"arquivo em fontes/ fora do índice: {arq.name}"))
                if not NOME_VALIDO.match(arq.name):
                    problemas.append(Problema(False, f"nome fora do padrão: {arq.name}"))
    return problemas
