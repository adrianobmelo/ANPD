"""Fontes oficiais em fontes/ e o índice fontes/index.json com hash.

Regra 1: nenhum conteúdo jurídico vem de memória de modelo. O que não está
aqui, com hash conferido, não existe para o sistema.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .db import pasta_fontes

NOME_VALIDO = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*\.(html|htm|pdf|txt|json)$")

API_NORMAS = "https://normas.leg.br/api/public/normas?urn={urn}&tipo_documento=maior-detalhe"
PAGINA_NORMAS = "https://normas.leg.br/?urn={urn}"
ORIGEM_NORMAS = "normas.leg.br (portal de legislação do Congresso Nacional)"

# Núcleo inicial. Fonte: dados estruturados do normas.leg.br, um registro por
# dispositivo com todas as versões datadas. O Planalto redireciona acessos de
# fora do Brasil para a página inicial, então não serve como fonte automática.
CATALOGO = [
    {"arquivo": "lei_13709_2018.json", "norma": "Lei 13.709/2018 (LGPD)",
     "urn": "urn:lex:br:federal:lei:2018-08-14;13709", "numero": "13.709"},
    {"arquivo": "lei_15352_2026.json", "norma": "Lei 15.352/2026",
     "urn": "urn:lex:br:federal:lei:2026-02-25;15352", "numero": "15.352"},
    {"arquivo": "lei_14133_2021.json", "norma": "Lei 14.133/2021 (licitações e contratos)",
     "urn": "urn:lex:br:federal:lei:2021-04-01;14133", "numero": "14.133"},
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


def _versoes_de_texto(dados: dict) -> list[str]:
    enc = dados.get("encoding") or []
    enc = enc if isinstance(enc, list) else [enc]
    return [f"{e.get('additionalType')} ({e.get('legislationLegalValue')})"
            for e in enc if isinstance(e, dict)]


def baixar(item: dict, timeout: int = 120) -> dict:
    """Baixa o JSON da norma no normas.leg.br e grava os bytes como vieram.

    O arquivo gravado é a resposta da API, sem nenhuma transformação; o hash
    vale para esses bytes. data_versao é a dateModified informada pela API
    (ou a data da lei, quando ela nunca foi alterada).
    """
    url = API_NORMAS.format(urn=item["urn"])
    req = urllib.request.Request(url, headers={"User-Agent": "estudo-anpd/0.1",
                                               "Accept": "application/json"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise ErroFonte(f"{url} respondeu {resp.status}")
                final = resp.geturl()
                conteudo = resp.read()
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if tentativa == 2:
                raise
            time.sleep(2 * (tentativa + 1))
    if final != url:
        raise ErroFonte(f"{url} redirecionou para {final}; nada foi gravado")
    try:
        dados = json.loads(conteudo)
    except ValueError:
        raise ErroFonte(f"{url} não devolveu JSON; nada foi gravado")
    if dados.get("legislationIdentifier") != item["urn"] or item["numero"] not in dados.get("headline", ""):
        raise ErroFonte(f"{url} devolveu outra norma ({dados.get('headline')}); nada foi gravado")
    if not dados.get("hasPart"):
        raise ErroFonte(f"{url} veio sem dispositivos; nada foi gravado")
    destino = pasta_fontes() / item["arquivo"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    if dados.get("dateModified"):
        versao = f"{dados['dateModified']} (última alteração segundo a API)"
    else:
        versao = f"{dados.get('legislationDate')} (data da lei; a API não registra alteração)"
    entrada = registrar(item["arquivo"], item["norma"], ORIGEM_NORMAS, url,
                        f"{versao}; obtido em {date.today().isoformat()}")
    entrada.update({
        "urn": item["urn"],
        "pagina": PAGINA_NORMAS.format(urn=item["urn"]),
        "titulo_oficial": dados.get("headline"),
        "versoes_de_texto_na_fonte": _versoes_de_texto(dados),
        "licenca": dados.get("license"),
    })
    entradas = [e for e in ler_index() if e["arquivo"] != item["arquivo"]] + [entrada]
    gravar_index(entradas)
    return entrada


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
