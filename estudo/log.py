"""estudo log, modo turbo. Uma linha por item, o mínimo de perguntas.

Gramática da linha (ordem livre depois da referência):

    57 C E           item 57, gabarito C, respondi E
    57 E             item já existe: só a resposta
    57 C B           deixei em branco (B ou -)
    57 C C 3         confiança 3 digitada (sem número, vale 2 assumida)
    57 C C ch        acertei chutando (chute_certo)
    57 C E dir       assunto por prefixo ou alias ('dir'), mantido para os próximos
    57 C E 90s       tempo de cronômetro externo, em segundos
    57 C E #nota     o resto da linha vira nota
    prova/57 C E     troca a fonte da sessão para 'prova'

O tipo de erro só é perguntado quando houve erro, e a pergunta nunca traz valor
pré-selecionado (regra 4). Chute certo é declarado por você com 'ch'.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

from . import topicos
from .db import agora
from .registro import TIPOS_ERRO_DE_ERRO, ErroRegistro, Registro, registrar

CONFIANCA_PADRAO = 2
RESPOSTA = {"c": "C", "e": "E", "b": "B", "-": "B"}
MENU_TIPO = "  ".join(f"{i} {t}" for i, t in enumerate(TIPOS_ERRO_DE_ERRO, start=1))


class LinhaInvalida(Exception):
    pass


Perguntar = Callable[[str], str]


@dataclass
class Linha:
    fonte: str | None = None
    referencia: str = ""
    letras: list[str] = field(default_factory=list)
    confianca: int | None = None
    chute: bool = False
    tempo_s: int | None = None
    assunto: str | None = None
    nota: str = ""


def interpretar(texto: str) -> Linha:
    texto = texto.strip()
    nota = ""
    if "#" in texto:
        texto, nota = texto.split("#", 1)
    tokens = texto.split()
    if not tokens:
        raise LinhaInvalida("linha vazia")
    l = Linha(nota=nota.strip())
    primeiro = tokens[0]
    if "/" in primeiro:
        l.fonte, l.referencia = primeiro.rsplit("/", 1)
    else:
        l.referencia = primeiro
    if not l.referencia:
        raise LinhaInvalida("falta a referência do item")
    for tok in tokens[1:]:
        baixo = tok.lower()
        if baixo in RESPOSTA:
            l.letras.append(RESPOSTA[baixo])
        elif re.fullmatch(r"[0-3]", tok):
            l.confianca = int(tok)
        elif baixo == "ch":
            l.chute = True
        elif re.fullmatch(r"\d+s", baixo):
            l.tempo_s = int(baixo[:-1])
        else:
            l.assunto = tok.lstrip("@")
    if len(l.letras) > 2:
        raise LinhaInvalida("no máximo duas letras: gabarito e resposta")
    if "B" in l.letras[:-1]:
        raise LinhaInvalida("gabarito é C ou E; branco só como resposta")
    return l


@dataclass
class Sessao:
    con: sqlite3.Connection
    perguntar: Perguntar
    fonte: str | None = None
    assunto_id: int | None = None
    registrados: int = 0
    saldo: int = 0

    def _escolher_assunto(self, termo: str) -> int | None:
        achados = topicos.buscar(self.con, termo)
        if len(achados) == 1:
            return achados[0].id
        if not achados:
            resp = self.perguntar(f"assunto '{termo}' não encontrado. Outro termo (Enter = sem assunto): ")
            return self._escolher_assunto(resp) if resp.strip() else None
        opcoes = "  ".join(f"{i} {t.codigo}" for i, t in enumerate(achados[:9], start=1))
        while True:
            resp = self.perguntar(f"'{termo}' é ambíguo: {opcoes}\nnúmero, outro termo ou Enter = sem assunto: ").strip()
            if not resp:
                return None
            if resp.isdigit() and 1 <= int(resp) <= min(len(achados), 9):
                return achados[int(resp) - 1].id
            return self._escolher_assunto(resp)

    def _tipo_erro(self) -> str:
        while True:
            resp = self.perguntar(f"tipo de erro: {MENU_TIPO}\n> ").strip()
            if resp.isdigit() and 1 <= int(resp) <= len(TIPOS_ERRO_DE_ERRO):
                return TIPOS_ERRO_DE_ERRO[int(resp) - 1]
            if resp in TIPOS_ERRO_DE_ERRO:
                return resp

    def _confundido(self) -> int:
        while True:
            termo = self.perguntar("assunto confundido: ").strip()
            if termo:
                achado = self._escolher_assunto(termo)
                if achado is not None:
                    return achado

    def processar(self, texto: str) -> str:
        l = interpretar(texto)
        if l.fonte:
            self.fonte = l.fonte
        if not self.fonte:
            raise LinhaInvalida("sem fonte: use fonte/ref na primeira linha ou --fonte")
        if l.assunto:
            self.assunto_id = self._escolher_assunto(l.assunto)

        item = self.con.execute(
            "SELECT gabarito, topic_id FROM items WHERE fonte = ? AND referencia = ?",
            (self.fonte, l.referencia),
        ).fetchone()
        if len(l.letras) == 2:
            gabarito, resposta = l.letras
        elif len(l.letras) == 1:
            resposta = l.letras[0]
            if item is None:
                while True:
                    g = self.perguntar(f"item {l.referencia} é novo. gabarito (C/E): ").strip().upper()
                    if g in ("C", "E"):
                        gabarito = g
                        break
            else:
                gabarito = item["gabarito"]
        else:
            raise LinhaInvalida("falta a resposta (C, E ou B)")

        if l.chute and resposta != gabarito:
            raise LinhaInvalida("'ch' é só para acerto; errou, então o tipo vem da pergunta")

        tipo = ""
        confundido = None
        if resposta != "B" and resposta != gabarito:
            tipo = self._tipo_erro()
            if tipo == "confusao":
                confundido = self._confundido()
        elif l.chute:
            tipo = "chute_certo"

        if item is not None and item["topic_id"] is not None:
            topic_id = item["topic_id"]
        else:
            topic_id = self.assunto_id
        t = topicos.por_id(self.con, topic_id)
        tc = topicos.por_id(self.con, confundido)

        r = Registro(
            data=agora(), fonte=self.fonte, referencia=l.referencia, gabarito=gabarito,
            arvore=t.arvore if t else "", topico=t.codigo if t else "",
            resposta=resposta,
            confianca=str(CONFIANCA_PADRAO if l.confianca is None else l.confianca),
            confianca_explicita="0" if l.confianca is None else "1",
            tempo_s=str(l.tempo_s) if l.tempo_s else "",
            tempo_origem="cronometro" if l.tempo_s else "",
            tipo_erro=tipo,
            arvore_confundido=tc.arvore if tc else "", topico_confundido=tc.codigo if tc else "",
            nota=l.nota,
        )
        registrar(self.con, r)
        self.registrados += 1
        pontos = 0 if resposta == "B" else (1 if resposta == gabarito else -1)
        self.saldo += pontos
        estado = {1: "certo", -1: "errado", 0: "branco"}[pontos]
        extra = f" {tipo}" if tipo else ""
        novo = " (novo, esboço)" if item is None else ""
        return (f"ok {self.fonte}/{l.referencia}{novo}: {estado}{extra} | "
                f"{topicos.rotulo(self.con, topic_id)} | sessão {self.registrados} itens, "
                f"saldo {self.saldo:+d}")


__all__ = ["Sessao", "interpretar", "LinhaInvalida", "ErroRegistro"]
