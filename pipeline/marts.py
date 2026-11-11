"""Etapa 3 do pipeline Olist: passagem de refined para marts.

Execução:
    uv run python -m pipeline.marts

M1. ESCOPO
    Lê de refined, escreve no schema marts. Nunca escreve em raw nem em
    refined. O schema marts é apagado e recriado a cada execução
    (DROP SCHEMA IF EXISTS marts CASCADE).
    Por quê: um mart cujo arquivo foi apagado não pode continuar existindo
    no banco.

M2. UM ARQUIVO, UMA TABELA
    Lê todos os sql/marts/*.sql em ordem alfabética.
    Nome da tabela = nome do arquivo sem a extensão e sem o prefixo numérico:
        sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
    Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
    Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais.
    O Python não altera, não monta e não completa a SQL.
    Por quê: a regra de negócio mora inteira no arquivo .sql.

M3. SAÍDA NA TELA
    Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
        ✓ marts.vendas_mensais        24 linhas
    Linha final com o número de marts e o total de linhas.
    stdout reconfigurado para utf-8.
    Por quê: a contagem lida do banco é a do que foi gravado de fato, e o
    ✓ e os acentos não podem quebrar no console do Windows.

M4. ERRO
    a) Antes de tudo: se faltar qualquer uma das tabelas de refined, lista
       quais, manda rodar "uv run python -m pipeline.refinamento" e encerra
       com sys.exit(1).
       Por quê: sem refined todo mart falharia, com uma mensagem que não
       aponta a causa.
    b) sql/marts/ sem nenhum arquivo: avisa e sys.exit(1).
       Por quê: apagar marts e não recriar nada derrubaria o dashboard em
       silêncio.
    c) Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois
       arquivos que dão o mesmo nome de tabela -> lista quais e
       sys.exit(1).
       Por quê: a ordem depende do prefixo, e dois arquivos com o mesmo
       nome fariam o segundo falhar (ou esconder o primeiro) no meio da
       execução.
    d) Um .sql falhou: mostra o nome do arquivo e a mensagem do DuckDB, não
       executa os seguintes, sys.exit(1).
       Por quê: o erro tem que apontar o arquivo a corrigir.
    e) Um mart voltou com zero linhas: mostra o nome e sys.exit(1).
       Por quê: mart vazio é quase sempre um JOIN que não casou, e um
       dashboard vazio parece um negócio parado.
    f) Tudo roda numa transação só: se qualquer passo falhar (inclusive o
       mart vazio), o schema marts volta a ser o da última execução que
       deu certo.
       Por quê: um schema pela metade quebra o dashboard sem avisar.

Critérios de aceite:
- Com um arquivo sql/marts/00_teste.sql contendo "SELECT 1 AS x", cria
  marts.teste com 1 linha.
- Apagar o arquivo e rodar de novo faz marts.teste desaparecer.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela,
  e marts continua exatamente como estava antes da execução.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import conectar, criar_schema

ORIGEM = "refined"
DESTINO = "marts"
PASTA_SQL = Path(__file__).resolve().parent.parent / "sql" / "marts"

# Lista fixa, igual ao TABELAS de pipeline/refinamento.py.
TABELAS_ORIGEM = [
    "pedidos",
    "itens_pedido",
    "pagamentos",
    "avaliacoes",
    "clientes",
    "vendedores",
    "produtos",
    "traducao_categorias",
    "geolocalizacao",
]

PREFIXO = re.compile(r"^\d{2}_(.+)$")


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def erro(*linhas: str) -> None:
    # Com a saída redirecionada o stdout tem buffer e o stderr não; sem o
    # flush, os ✓ já impressos apareceriam depois da mensagem de erro.
    sys.stdout.flush()
    for linha in linhas:
        print(linha, file=sys.stderr)


def tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [t for t in TABELAS_ORIGEM if t not in existentes]


def nomear(arquivos: list[Path]) -> tuple[list[tuple[Path, str]], list[str]]:
    """Devolve (arquivo, tabela) de cada .sql e a lista de problemas (M4c)."""
    marts: list[tuple[Path, str]] = []
    sem_prefixo: list[str] = []
    por_nome: dict[str, list[str]] = {}
    for arq in arquivos:
        m = PREFIXO.match(arq.stem)
        if m is None:
            sem_prefixo.append(arq.name)
            continue
        marts.append((arq, m.group(1)))
        # O DuckDB não diferencia maiúscula de minúscula em identificador,
        # nem entre aspas: 01_Vendas e 02_vendas viram a mesma tabela.
        por_nome.setdefault(m.group(1).lower(), []).append(arq.name)

    problemas = [f"  {n}: sem prefixo NN_" for n in sem_prefixo]
    for nome, donos in por_nome.items():
        if len(donos) > 1:
            problemas.append(f"  {', '.join(donos)}: todos viram {DESTINO}.{nome}")
    return marts, problemas


def ler_sql(arq: Path) -> str:
    # utf-8-sig descarta o BOM que editores do Windows gravam no início;
    # com ele o DuckDB recusaria a primeira palavra do arquivo.
    texto = arq.read_text(encoding="utf-8-sig").rstrip()
    return texto.removesuffix(";").rstrip()


def checar_um_select(con: duckdb.DuckDBPyConnection, sql: str) -> str | None:
    # execute() roda todos os comandos do texto: "SELECT 1; DROP TABLE
    # refined.pedidos" apagaria refined (M1). Só analisa, não executa nada.
    comandos = con.extract_statements(sql)
    if len(comandos) != 1 or comandos[0].type != duckdb.StatementType.SELECT:
        tipos = ", ".join(c.type.name for c in comandos) or "nenhum"
        return f"o arquivo deve ter um único SELECT; encontrado: {tipos}"
    return None


def criar_marts(con: duckdb.DuckDBPyConnection, marts: list[tuple[Path, str]]) -> None:
    largura = max(len(f"{DESTINO}.{nome}") for _, nome in marts)
    total = 0
    con.begin()
    try:
        con.execute(f'DROP SCHEMA IF EXISTS "{DESTINO}" CASCADE').complete()
        criar_schema(con, DESTINO)
        for arq, nome in marts:
            destino = f'"{DESTINO}"."{nome}"'
            caminho = f"sql/marts/{arq.name}"
            sql = ler_sql(arq)
            try:
                problema = checar_um_select(con, sql)
                if problema is None:
                    con.execute(f"CREATE TABLE {destino} AS {sql}").complete()
            except duckdb.Error as e:
                problema = str(e)
            if problema is not None:
                erro(
                    f"\n✗ Falhou: {caminho}",
                    problema,
                    f"\nNada foi gravado: {DESTINO} continua como na última "
                    "execução que deu certo.",
                )
                sys.exit(1)

            linhas = con.execute(f"SELECT count(*) FROM {destino}").fetchall()[0][0]
            if linhas == 0:
                erro(
                    f"\n✗ {DESTINO}.{nome} voltou com zero linhas ({caminho}).",
                    "Confira os JOINs e filtros do arquivo.",
                    f"\nNada foi gravado: {DESTINO} continua como na última "
                    "execução que deu certo.",
                )
                sys.exit(1)

            total += linhas
            rotulo = "linha" if linhas == 1 else "linhas"
            alvo = f"{DESTINO}.{nome}"
            print(f"✓ {alvo:<{largura}}  {milhar(linhas):>9} {rotulo}")
        con.commit()
    except BaseException:
        # Inclui o SystemExit dos erros acima: o DROP SCHEMA também volta.
        con.rollback()
        raise

    rotulo = "mart" if len(marts) == 1 else "marts"
    print(f"\n{len(marts)} {rotulo}, {milhar(total)} linhas no total")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            erro(f"Tabelas faltando em {ORIGEM}:")
            erro(*(f"  {ORIGEM}.{t}" for t in faltando))
            erro("Rode o refinamento antes: uv run python -m pipeline.refinamento")
            sys.exit(1)

        arquivos = sorted(PASTA_SQL.glob("*.sql"), key=lambda p: p.name)
        if not arquivos:
            erro("Nenhum arquivo .sql em sql/marts/. Nada foi alterado.")
            sys.exit(1)

        marts, problemas = nomear(arquivos)
        if problemas:
            erro("Arquivos inválidos em sql/marts/. Nenhuma SQL foi executada:")
            erro(*problemas)
            sys.exit(1)

        criar_marts(con, marts)
    finally:
        con.close()


if __name__ == "__main__":
    main()
