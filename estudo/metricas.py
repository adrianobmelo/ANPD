"""Motor de saldo. Tudo calculado na hora a partir de v_tentativas; nada é gravado.

Constantes ficam aqui, num lugar só, e são impressas no cabeçalho do relatório.
Elas são escolha inicial, não vêm de dado.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

Z = 1.96                 # Wilson com 95% de confiança
MIN_RANKING = 5          # respondidos mínimos para entrar no ranking de prioridade
MIN_CONCLUSAO = 10       # abaixo disso a linha é marcada como amostra insuficiente
PESO_REINCIDENCIA = 0.1  # cada item reincidente soma 0,1 ao fator
MAX_REINCIDENCIA = 5     # teto: fator máximo 1,5
MEIA_VIDA_DIAS = 30      # recência: fator cai de 1,0 a 0,75 em 30 dias, tende a 0,5
MIN_FALSA_CONFIANCA = 10 # respondidos com confiança 2 ou 3 para avaliar falsa confiança
FATOR_FALSA_CONFIANCA = 1.25

CONSTANTES = {
    "Z (Wilson 95%)": Z,
    "mínimo de respondidos para o ranking": MIN_RANKING,
    "mínimo para conclusão": MIN_CONCLUSAO,
    "peso por item reincidente": PESO_REINCIDENCIA,
    "teto de reincidentes": MAX_REINCIDENCIA,
    "meia-vida da recência (dias)": MEIA_VIDA_DIAS,
    "mínimo para falsa confiança": MIN_FALSA_CONFIANCA,
    "fator de falsa confiança": FATOR_FALSA_CONFIANCA,
}


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """Intervalo de Wilson para a proporção k/n. n = 0 devolve (0, 1)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centro - margem) / den), min(1.0, (centro + margem) / den)


def _dia(data: str) -> date:
    return date.fromisoformat(data[:10])


def tentativas(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM v_tentativas ORDER BY data, attempt_id").fetchall()


# ---------------------------------------------------------------- saldo geral

@dataclass
class Saldo:
    total: int = 0
    respondidos: int = 0
    acertos: int = 0
    erros: int = 0
    brancos: int = 0

    @property
    def saldo(self) -> int:
        return self.acertos - self.erros

    @property
    def taxa_resposta(self) -> float | None:
        return self.respondidos / self.total if self.total else None

    @property
    def insuficiente(self) -> bool:
        return self.respondidos < MIN_CONCLUSAO

    def somar(self, t: sqlite3.Row) -> None:
        self.total += 1
        if t["resposta"] == "B":
            self.brancos += 1
            return
        self.respondidos += 1
        if t["acerto"] == 1:
            self.acertos += 1
        else:
            self.erros += 1


def saldo_geral(ts: list[sqlite3.Row]) -> Saldo:
    s = Saldo()
    for t in ts:
        s.somar(t)
    return s


def saldo_por(ts: list[sqlite3.Row], chave) -> dict:
    grupos: dict = defaultdict(Saldo)
    for t in ts:
        grupos[chave(t)].somar(t)
    return dict(grupos)


# ---------------------------------------------------------- curva de confiança

@dataclass
class NivelConfianca:
    nivel: int
    saldo: Saldo
    intervalo: tuple[float, float]

    @property
    def veredito(self) -> str:
        """Responder vale a pena quando P(acerto) > 0,5: ganho esperado = 2p - 1."""
        if self.saldo.respondidos < MIN_CONCLUSAO:
            return "amostra insuficiente"
        baixo, alto = self.intervalo
        if baixo > 0.5:
            return "responder compensa"
        if alto < 0.5:
            return "branco compensa"
        return "inconclusivo (intervalo inclui 50%)"


def curva_confianca(ts: list[sqlite3.Row], somente_explicita: bool = False) -> list[NivelConfianca]:
    niveis = []
    for nivel in range(4):
        s = Saldo()
        for t in ts:
            if t["confianca"] == nivel and (t["confianca_explicita"] or not somente_explicita):
                s.somar(t)
        niveis.append(NivelConfianca(nivel, s, wilson(s.acertos, s.respondidos)))
    return niveis


def ponto_de_corte(curva: list[NivelConfianca]) -> str:
    """Menor nível a partir do qual responder compensa em todos os níveis acima."""
    compensam = [n.veredito == "responder compensa" for n in curva]
    for nivel in range(4):
        if all(compensam[nivel:]):
            return f"responder a partir da confiança {nivel}"
    if any(n.saldo.respondidos < MIN_CONCLUSAO for n in curva):
        return "sem ponto de corte: há nível com amostra insuficiente"
    return "sem ponto de corte: nenhum nível superior compensa com segurança"


# ------------------------------------------------------------------- timidez

def timidez(ts: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Brancos com confiança 2 ou 3: pontos que eu tinha e não levei."""
    return [t for t in ts if t["resposta"] == "B" and t["confianca"] >= 2]


def tipos_de_erro(ts: list[sqlite3.Row]) -> dict[str, int]:
    from .registro import TIPOS_ERRO
    contagem = {tipo: 0 for tipo in TIPOS_ERRO}
    for t in ts:
        if t["tipo_erro"]:
            contagem[t["tipo_erro"]] += 1
    return contagem


def evolucao_semanal(ts: list[sqlite3.Row]) -> list[tuple[str, Saldo]]:
    semanas: dict[str, Saldo] = defaultdict(Saldo)
    for t in ts:
        ano, semana, _ = _dia(t["data"]).isocalendar()
        semanas[f"{ano}-S{semana:02d}"].somar(t)
    return sorted(semanas.items())


# ---------------------------------------------------------------- por assunto

@dataclass
class Assunto:
    topico: int | None
    saldo: Saldo = field(default_factory=Saldo)
    erros_revisao: int = 0
    reincidentes: int = 0
    ultimo_erro: str | None = None
    conf_alta: Saldo = field(default_factory=Saldo)

    def dias_desde_erro(self, hoje: date) -> int | None:
        return None if self.ultimo_erro is None else (hoje - _dia(self.ultimo_erro)).days

    @property
    def wilson_erro(self) -> tuple[float, float]:
        return wilson(self.erros_revisao, self.saldo.respondidos)

    @property
    def falsa_confianca(self) -> bool | None:
        """None = amostra insuficiente para dizer."""
        if self.conf_alta.respondidos < MIN_FALSA_CONFIANCA:
            return None
        return self.conf_alta.saldo < 0

    def fator_reincidencia(self) -> float:
        return 1 + PESO_REINCIDENCIA * min(self.reincidentes, MAX_REINCIDENCIA)

    def fator_recencia(self, hoje: date) -> float:
        d = self.dias_desde_erro(hoje)
        if d is None:
            return 0.5
        return 0.5 + 0.5 * 2 ** (-max(d, 0) / MEIA_VIDA_DIAS)

    def prioridade(self, hoje: date) -> float:
        p = self.wilson_erro[0] * self.fator_reincidencia() * self.fator_recencia(hoje)
        if self.falsa_confianca:
            p *= FATOR_FALSA_CONFIANCA
        return p


def por_assunto(ts: list[sqlite3.Row]) -> dict[int | None, Assunto]:
    assuntos: dict[int | None, Assunto] = {}
    erros_por_item: dict[tuple[int | None, int], int] = defaultdict(int)
    for t in ts:
        a = assuntos.setdefault(t["topico"], Assunto(t["topico"]))
        a.saldo.somar(t)
        if t["resposta"] != "B" and t["confianca"] >= 2:
            a.conf_alta.somar(t)
        if t["erro_revisao"] == 1:
            a.erros_revisao += 1
            erros_por_item[(t["topico"], t["item_id"])] += 1
            if a.ultimo_erro is None or t["data"] > a.ultimo_erro:
                a.ultimo_erro = t["data"]
    for (topico, _), n in erros_por_item.items():
        if n >= 2:
            assuntos[topico].reincidentes += 1
    return assuntos


@dataclass
class Prioridade:
    assunto: Assunto
    valor: float
    porque: str


def explicar(a: Assunto, hoje: date) -> str:
    baixo, _ = a.wilson_erro
    d = a.dias_desde_erro(hoje)
    recencia = "sem erro registrado" if d is None else f"último erro há {d} dias"
    fc = a.falsa_confianca
    if fc is None:
        falsa = f"falsa confiança: amostra {a.conf_alta.respondidos}, insuficiente"
    elif fc:
        falsa = (f"falsa confiança: saldo {a.conf_alta.saldo:+d} em "
                 f"{a.conf_alta.respondidos} com conf. 2-3 (x{FATOR_FALSA_CONFIANCA:.2f})")
    else:
        falsa = f"sem falsa confiança (saldo {a.conf_alta.saldo:+d} com conf. 2-3)"
    return (
        f"erro {a.erros_revisao}/{a.saldo.respondidos} (Wilson {baixo:.2f})  "
        f"reincidentes {a.reincidentes} (x{a.fator_reincidencia():.2f})  "
        f"{recencia} (x{a.fator_recencia(hoje):.2f})  {falsa}"
    )


def ranking(ts: list[sqlite3.Row], hoje: date) -> tuple[list[Prioridade], list[Assunto]]:
    """Devolve (ranking, assuntos com amostra insuficiente para o ranking)."""
    elegiveis, insuficientes = [], []
    for a in por_assunto(ts).values():
        if a.topico is None:
            continue
        if a.saldo.respondidos >= MIN_RANKING:
            elegiveis.append(Prioridade(a, a.prioridade(hoje), explicar(a, hoje)))
        elif a.erros_revisao > 0:
            insuficientes.append(a)
    elegiveis.sort(key=lambda p: p.valor, reverse=True)
    insuficientes.sort(key=lambda a: (a.erros_revisao, a.saldo.respondidos), reverse=True)
    return elegiveis, insuficientes


def pares(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM v_pares ORDER BY erros_confusao DESC, ultimo_erro DESC"
    ).fetchall()
