"""CLI: estudo log | import | classificar | relatorio | revisar | auditoria | ..."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from . import arvores, auditoria, fontes, importar as imp, log as logmod, relatorio as rel
from . import revisar as rev, topicos
from .db import caminho_banco, conectar
from .registro import ErroRegistro, classificar_item, diario_classificacoes, diario_tentativas

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="Registro de itens Cebraspe e motor de saldo (concurso ANPD).")
arvore_app = typer.Typer(no_args_is_help=True, help="Árvore de assuntos.")
fontes_app = typer.Typer(no_args_is_help=True, help="Fontes oficiais em fontes/.")
app.add_typer(arvore_app, name="arvore")
app.add_typer(fontes_app, name="fontes")


def _ler(prompt: str) -> str:
    typer.echo(prompt, nl=False)
    linha = sys.stdin.readline()
    if linha == "":
        raise EOFError
    return linha.rstrip("\n")


def _falha(msg: str, codigo: int = 1) -> None:
    typer.echo(f"erro: {msg}", err=True)
    raise typer.Exit(codigo)


# ----------------------------------------------------------------------- log

@app.command()
def log(
    fonte: Optional[str] = typer.Option(None, "--fonte", "-f", help="Prova da sessão."),
    assunto: Optional[str] = typer.Option(None, "--assunto", "-a", help="Assunto inicial."),
):
    """Registra itens em modo turbo. 'q' ou linha vazia encerra; '?' mostra a sintaxe."""
    con = conectar()
    sessao = logmod.Sessao(con, _ler, fonte=fonte)
    try:
        if assunto:
            sessao.assunto_id = sessao._escolher_assunto(assunto)
        while True:
            cabeca = f"[{sessao.fonte or 'sem fonte'} | {topicos.rotulo(con, sessao.assunto_id)}] > "
            linha = _ler(cabeca).strip()
            if linha in ("", "q"):
                break
            if linha == "?":
                typer.echo(logmod.__doc__)
                continue
            try:
                typer.echo(sessao.processar(linha))
            except (logmod.LinhaInvalida, ErroRegistro, sqlite3.IntegrityError) as e:
                typer.echo(f"  não registrado: {e}")
    except EOFError:
        pass
    typer.echo(f"{sessao.registrados} itens registrados, saldo da sessão {sessao.saldo:+d}")


# -------------------------------------------------------------------- import

@app.command("import")
def importar_cmd(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False),
    dry_run: bool = typer.Option(False, "--dry-run", help="Valida tudo e não grava nada."),
):
    """Importa tentativas de CSV, em transação única: ou entra tudo, ou nada."""
    con = conectar()
    res = imp.importar(con, arquivo, dry_run=dry_run)
    typer.echo(f"{res.lidas} linhas lidas, {res.aceitas} válidas, {len(res.rejeitadas)} rejeitadas")
    for n, motivo in res.rejeitadas:
        typer.echo(f"  linha {n}: {motivo}")
    if res.rejeitadas:
        typer.echo("nada foi gravado")
        raise typer.Exit(1)
    typer.echo("dry-run: nada foi gravado" if dry_run else "gravado no banco e no diário")


# --------------------------------------------------------------- classificar

@app.command()
def classificar():
    """Percorre a fila de itens sem assunto. Enter pula, 'q' sai."""
    con = conectar()
    fila = con.execute(
        "SELECT id, fonte, referencia, gabarito, enunciado FROM items"
        " WHERE topic_id IS NULL ORDER BY fonte, referencia"
    ).fetchall()
    typer.echo(f"{len(fila)} itens sem assunto")
    sessao = logmod.Sessao(con, _ler)
    feitos = 0
    try:
        for item in fila:
            desc = f"{item['fonte']}/{item['referencia']} (gabarito {item['gabarito']})"
            if item["enunciado"]:
                desc += f": {item['enunciado'][:200]}"
            termo = _ler(f"{desc}\nassunto: ").strip()
            if termo == "q":
                break
            if not termo:
                continue
            topic_id = sessao._escolher_assunto(termo)
            if topic_id is not None:
                classificar_item(con, item["id"], topic_id)
                feitos += 1
    except EOFError:
        pass
    typer.echo(f"{feitos} itens classificados")


# ----------------------------------------------------------------- relatório

@app.command()
def relatorio():
    """Saldo, curva de confiança, timidez, erros, pares e prioridades."""
    typer.echo(rel.gerar(conectar(), date.today()))


@app.command()
def revisar(limite: int = typer.Option(20, help="Quantos itens mostrar.")):
    """O que volta hoje, com o motivo ao lado."""
    con = conectar()
    itens = rev.itens_para_revisar(con, date.today(), limite)
    if not itens:
        typer.echo("nada para revisar: nenhum item com erro ou chute certo pendente")
    for r in itens:
        typer.echo(f"{r.fonte}/{r.referencia:<6} {topicos.rotulo(con, r.topico):<28} {r.motivo}")


@app.command("auditoria")
def auditoria_cmd():
    """Inconsistências. Sai com código 1 quando há erro crítico."""
    con = conectar()
    problemas = auditoria.auditar(con)
    criticos = [p for p in problemas if p.critico]
    for p in problemas:
        typer.echo(("CRÍTICO " if p.critico else "aviso   ") + p.mensagem)
    typer.echo("nota: cartão sem dispositivo de origem é verificado a partir da Fase 2")
    typer.echo(f"{len(criticos)} críticos, {len(problemas) - len(criticos)} avisos")
    if criticos:
        raise typer.Exit(1)



# --------------------------------------------------------------- reconstruir

@app.command()
def reconstruir(
    destino: Optional[Path] = typer.Option(None, help="Banco novo. Padrão: o banco configurado."),
    forcar: bool = typer.Option(False, "--forcar", help="Apaga o banco de destino se existir."),
):
    """Recria o banco do zero a partir de dados/ (árvores, mapas, diários)."""
    alvo = destino or caminho_banco()
    if alvo.exists():
        if not forcar:
            _falha(f"{alvo} existe; use --forcar para apagá-lo e reconstruir")
        alvo.unlink()
    con = conectar(alvo)
    arvores.reaplicar(con)
    if diario_tentativas().exists():
        res = imp.importar(con, diario_tentativas(), dry_run=False, diario=False)
        if res.rejeitadas:
            for n, motivo in res.rejeitadas:
                typer.echo(f"  tentativas.csv linha {n}: {motivo}")
            _falha("diário de tentativas com linhas inválidas; banco parcial descartado")
    if diario_classificacoes().exists():
        imp.importar_classificacoes(con, diario_classificacoes())
    n = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    typer.echo(f"banco reconstruído em {alvo}: {n} tentativas")


# -------------------------------------------------------------------- árvore

@arvore_app.command("carregar")
def arvore_carregar(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False),
    nome: str = typer.Option(..., "--nome"),
    ativar: bool = typer.Option(True, "--ativar/--nao-ativar"),
):
    """Carrega árvore nova de CSV (codigo,nome,disciplina,parent_codigo,aliases)."""
    try:
        arvores.carregar(conectar(), arquivo, nome, ativar)
    except topicos.ErroTopico as e:
        _falha(str(e))
    typer.echo(f"árvore '{nome}' carregada" + (" e ativada" if ativar else ""))


@arvore_app.command("ativar")
def arvore_ativar(nome: str):
    try:
        arvores.ativar(conectar(), nome)
    except topicos.ErroTopico as e:
        _falha(str(e))
    typer.echo(f"árvore '{nome}' ativa")


@arvore_app.command("mapear")
def arvore_mapear(arquivo: Path = typer.Argument(..., exists=True, dir_okay=False)):
    """Mapeia assuntos de uma árvore para outra (de_arvore,de_codigo,para_arvore,para_codigo)."""
    try:
        n = arvores.mapear(conectar(), arquivo)
    except topicos.ErroTopico as e:
        _falha(str(e))
    typer.echo(f"{n} mapeamentos gravados")


@arvore_app.command("sumario")
def arvore_sumario(
    fonte: str = typer.Argument(..., help="Arquivo em fontes/, ex.: lei_13709_2018.html"),
    prefixo: str = typer.Option(..., "--prefixo", help="Código raiz, ex.: LGPD"),
    disciplina: str = typer.Option(..., "--disciplina"),
    nome: str = typer.Option(..., "--nome", help="Nome do assunto raiz."),
    saida: Path = typer.Option(..., "--saida"),
):
    """Gera CSV de árvore com títulos, capítulos e seções do arquivo de fonte."""
    caminho = fontes.pasta_fontes() / fonte
    if not caminho.exists():
        _falha(f"fonte não encontrada: {caminho}")
    if fonte not in {e["arquivo"] for e in fontes.ler_index()}:
        _falha(f"{fonte} não está em fontes/index.json; registre antes")
    linhas = arvores.sumario(caminho, prefixo, disciplina, nome)
    arvores.gravar_sumario(linhas, saida)
    typer.echo(f"{len(linhas)} assuntos em {saida}; revise antes de carregar")


@arvore_app.command("listar")
def arvore_listar():
    con = conectar()
    for r in con.execute(
        "SELECT t.codigo, t.nome, t.disciplina, group_concat(a.alias, '|') AS aliases"
        " FROM topics t JOIN topic_trees tt ON tt.id = t.tree_id AND tt.ativa = 1"
        " LEFT JOIN topic_aliases a ON a.topic_id = t.id GROUP BY t.id ORDER BY t.codigo"
    ):
        typer.echo(f"{r['codigo']:<24} {r['nome']}" + (f"  [{r['aliases']}]" if r["aliases"] else ""))


# -------------------------------------------------------------------- fontes

@fontes_app.command("baixar")
def fontes_baixar():
    """Baixa o núcleo (LGPD, 15.352, 14.133) das URLs oficiais do Planalto."""
    falhas = 0
    for item in fontes.CATALOGO:
        try:
            e = fontes.baixar(item)
            typer.echo(f"ok {e['arquivo']} sha256 {e['sha256'][:12]}")
        except Exception as ex:  # rede, HTTP, redirecionamento
            falhas += 1
            typer.echo(f"falhou {item['arquivo']}: {ex}")
    if falhas:
        raise typer.Exit(1)


@fontes_app.command("registrar")
def fontes_registrar(
    arquivo: str,
    norma: str = typer.Option(..., "--norma"),
    orgao: str = typer.Option(..., "--orgao"),
    url: str = typer.Option(..., "--url"),
    data_versao: str = typer.Option(..., "--data-versao"),
):
    """Registra no índice um arquivo que você colocou em fontes/."""
    try:
        e = fontes.registrar(arquivo, norma, orgao, url, data_versao)
    except fontes.ErroFonte as ex:
        _falha(str(ex))
    typer.echo(f"ok {e['arquivo']} sha256 {e['sha256'][:12]}")


if __name__ == "__main__":
    app()
