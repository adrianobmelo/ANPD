"""Texto de leitura gerado do JSON do normas.leg.br, sem nenhuma redação própria.

Cada linha é o rótulo e o texto literais da versão mais recente do dispositivo,
seguidos da norma que deu a redação, como a fonte informa. Dispositivos que a
lei alteradora mudou e que a consolidação não acompanhou aparecem num
confronto à parte, com as duas redações lado a lado.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .fontes import ler_index, pasta_fontes, sha256

NIVEL_TITULO = {"livro": 2, "parte": 2, "titulo": 2, "capitulo": 2, "secao": 3, "subsecao": 4}
RECUO = {"artigo": 0, "caput": 0, "paragrafo": 0, "inciso": 1, "alinea": 2, "item": 3, "pena": 1}
IGNORAR = {"componente.autonomo.articulado", "articulacao", "bloco.de.alteracao", "omissis",
           "assinaturas"}


@dataclass
class Dispositivo:
    id: str            # identificador sem o sufixo de origem (",mpv-..." etc.)
    tipo: str
    rotulo: str
    texto: str
    data: str
    redacao_de: str    # norma que deu a redação atual, quando a fonte informa
    n_versoes: int


def limpar(t: str | None) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", t or "")).split())


def _versoes(no: dict) -> list[dict]:
    we = no.get("workExample") or []
    return we if isinstance(we, list) else [we]


def dispositivos(caminho: Path) -> list[Dispositivo]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    brutos: list[tuple[str, str, dict]] = []

    def visitar(o) -> None:
        if isinstance(o, list):
            for x in o:
                visitar(x)
            return
        if not isinstance(o, dict):
            return
        if o.get("workExample"):
            ident = o["legislationIdentifier"].split("!", 1)[-1]
            tipo = (o.get("legislationType") or {}).get("@id", "").rsplit(":", 1)[-1]
            brutos.append((ident, tipo, o))
        if "hasPart" in o:
            visitar(o["hasPart"])

    visitar(dados.get("hasPart"))

    # A fonte guarda o mesmo dispositivo uma vez por norma de origem (por exemplo,
    # a medida provisória e a lei de conversão). Fica a ocorrência cuja versão
    # mais recente é a mais nova; no empate, a que não vem de medida provisória.
    escolhido: dict[str, tuple[str, dict, dict]] = {}
    ordem: list[str] = []
    for ident, tipo, no in brutos:
        base = ident.split(",")[0]
        atual = max(_versoes(no), key=lambda w: w.get("legislationDate", ""))
        chave = (atual.get("legislationDate", ""), "mpv" not in ident)
        if base not in escolhido:
            ordem.append(base)
            escolhido[base] = (tipo, no, atual)
        else:
            _, _, antigo = escolhido[base]
            antigo_ident = escolhido[base][1]["legislationIdentifier"]
            if chave > (antigo.get("legislationDate", ""), "mpv" not in antigo_ident):
                escolhido[base] = (tipo, no, atual)

    saida = []
    for base in ordem:
        tipo, no, atual = escolhido[base]
        if base in ("", "ementa", "preambulo", "fecho") and tipo in IGNORAR:
            continue
        if limpar(atual.get("text")).endswith("(Suprimido)") or \
                (atual.get("name") or "").strip().endswith("(Suprimido)"):
            continue  # texto de medida provisória que não foi convertido em lei
        cons = atual.get("legislationConsolidates") or {}
        saida.append(Dispositivo(
            id=base, tipo=tipo, rotulo=(atual.get("name") or "").strip(),
            texto=limpar(atual.get("text")), data=atual.get("legislationDate", ""),
            redacao_de=cons.get("name", "") if isinstance(cons, dict) else "",
            n_versoes=len(_versoes(no)),
        ))
    return _ordenar_irmaos(saida)


def _chave(ident: str) -> tuple:
    ultimo = ident.rsplit("_", 1)[-1]
    m = re.fullmatch(r"([a-z]+)(\d+)u?(?:-(\d+))?", ultimo)
    if not m:
        return (ultimo, 0, 0)
    return (m.group(1), int(m.group(2)), int(m.group(3) or 0))


def _ordenar_irmaos(ds: list[Dispositivo]) -> list[Dispositivo]:
    """A fonte acrescenta dispositivos novos (V-A, V-B) depois dos antigos.
    Reordena cada sequência de irmãos do mesmo tipo pelo número e pela letra."""
    saida: list[Dispositivo] = []
    i = 0
    while i < len(ds):
        pai = ds[i].id.rsplit("_", 1)[0] if "_" in ds[i].id else ""
        j = i
        while (j < len(ds) and ds[j].tipo == ds[i].tipo and ds[j].tipo in ("inciso", "alinea", "paragrafo")
               and (ds[j].id.rsplit("_", 1)[0] if "_" in ds[j].id else "") == pai):
            j += 1
        if j - i > 1:
            saida.extend(sorted(ds[i:j], key=lambda d: _chave(d.id)))
            i = j
        else:
            saida.append(ds[i])
            i += 1
    return saida


@dataclass
class Confronto:
    id: str
    rotulo: str
    texto_alteradora: str
    texto_consolidado: str | None
    data_consolidado: str | None

    @property
    def situacao(self) -> str:
        if self.texto_consolidado is None:
            return "ausente na consolidação"
        if _norm(self.texto_consolidado) == _norm(self.texto_alteradora):
            return "consolidação igual à lei alteradora"
        return "DIVERGE: a consolidação não traz a redação da lei alteradora"


def _norm(t: str) -> str:
    t = t.replace("–", "-").replace("“", '"').replace("”", '"')
    return re.sub(r"[\s;.,]+$", "", " ".join(t.split())).lower()


def confrontar(lei: list[Dispositivo], alteradora: list[Dispositivo], prefixo: str) -> list[Confronto]:
    """Compara cada dispositivo do bloco de alteração com a versão da consolidação."""
    por_id = {d.id: d for d in lei}
    saida = []
    for d in alteradora:
        if not d.id.startswith(prefixo) or d.tipo in IGNORAR:
            continue
        alvo = d.id[len(prefixo):]
        texto = " ".join(x for x in (d.rotulo if d.tipo in NIVEL_TITULO else "", d.texto) if x)
        if not texto or set(texto) <= set(". "):
            continue  # omissis ou só o rótulo do artigo
        c = por_id.get(alvo)
        consolidado = None
        if c is not None:
            consolidado = " ".join(x for x in (c.rotulo if c.tipo in NIVEL_TITULO else "", c.texto) if x)
        saida.append(Confronto(alvo, d.rotulo, texto, consolidado, c.data if c else None))
    return saida


def _linha(d: Dispositivo, marcar: str) -> str:
    nota = ""
    if d.redacao_de:
        nota = f" _(redação: {d.redacao_de})_"
    marca = f" **[{marcar}]**" if marcar and marcar in d.redacao_de.replace("nº ", "") else ""
    corpo = " ".join(x for x in (d.rotulo, d.texto) if x)
    return "  " * RECUO.get(d.tipo, 0) + corpo + nota + marca


def gerar_markdown(lei_arq: str, alteradora_arq: str | None, titulo: str,
                   prefixo_alteracao: str = "art1_cpt_alt1_", marcar: str = "") -> str:
    pasta = pasta_fontes()
    index = {e["arquivo"]: e for e in ler_index()}
    for arq in filter(None, (lei_arq, alteradora_arq)):
        if arq not in index:
            raise FileNotFoundError(f"{arq} não está em fontes/index.json")
        if sha256(pasta / arq) != index[arq]["sha256"]:
            raise ValueError(f"{arq} mudou desde o registro (hash divergente); rode a auditoria")
    lei = dispositivos(pasta / lei_arq)
    out = [f"# {titulo}", ""]
    e = index[lei_arq]
    out += [
        "Arquivo gerado por `estudo leitura`. Não edite: rode o comando de novo.",
        "",
        f"Fonte: `fontes/{lei_arq}` ({e['orgao']}), versão {e['data_versao']},",
        f"SHA-256 `{e['sha256'][:16]}`. Página: {e.get('pagina', e['url'])}",
        "",
        "Todo o texto abaixo é copiado da fonte, sem redação própria. A fonte marca a",
        "compilação como texto sem valor oficial; o texto oficial é o do Diário Oficial.",
        "Ao lado de cada dispositivo alterado aparece a norma que deu a redação atual,",
        "como a fonte informa.",
        "",
    ]
    if alteradora_arq:
        alt = dispositivos(pasta / alteradora_arq)
        conf = confrontar(lei, alt, prefixo_alteracao)
        divergentes = [c for c in conf if not c.situacao.startswith("consolidação igual")]
        ea = index[alteradora_arq]
        out += [f"## Confronto com {ea['norma']}", ""]
        out += [f"{len(conf)} dispositivos alterados pela lei; "
                f"{len(conf) - len(divergentes)} conferem com a consolidação, "
                f"{len(divergentes)} não confere{'m' if len(divergentes) != 1 else ''}.", ""]
        for c in divergentes:
            out += [f"### {c.id}: {c.situacao}", "",
                    f"Redação da {ea['norma']} (vale esta):", "", f"> {c.texto_alteradora}", "",
                    f"O que a consolidação traz (versão de {c.data_consolidado}):", "",
                    f"> {c.texto_consolidado or '(nada)'}", ""]
        if conf:
            out += ["Dispositivos conferidos:", ""]
            out += [f"- `{c.id}`: {c.situacao}" for c in conf]
            out.append("")
    out += ["## Texto", ""]
    aviso = {}
    if alteradora_arq:
        aviso = {c.id: f"> Desatualizado na consolidação. Redação da {ea['norma']}: {c.texto_alteradora}"
                 for c in divergentes}
    for d in lei:
        if d.tipo in NIVEL_TITULO:
            out += ["#" * NIVEL_TITULO[d.tipo] + f" {d.rotulo} - {d.texto}".rstrip(" -"), ""]
            if d.id in aviso:
                out += [aviso[d.id], ""]
            continue
        if d.id in aviso:
            out += [aviso[d.id], ""]
        elif d.tipo == "caput" and out and out[-1].startswith("**Art"):
            out[-1] = out[-1] + " " + _linha(d, marcar).lstrip()
            out.append("")
        elif d.tipo == "artigo":
            out.append(f"**{d.rotulo}**" + (f" {d.texto}" if d.texto else ""))
        elif d.tipo in ("ementa", "preambulo", "fecho"):
            out += [d.texto, ""]
        else:
            out += [_linha(d, marcar), ""]
    return "\n".join(out).rstrip() + "\n"
