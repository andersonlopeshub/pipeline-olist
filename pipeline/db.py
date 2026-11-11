"""Conexão com o banco do pipeline Olist.

Módulo importado pelas quatro etapas do curso. Expõe exatamente isto:

    PASTA_RAW                          Path da pasta raw/ com os nove .csv.gz
    conectar()                         abre o olist.duckdb, criando se faltar
    criar_schema(con, nome)            CREATE SCHEMA IF NOT EXISTS
    gravar(con, df, schema, tabela)    grava e devolve a contagem lida do banco

D1. CAMINHOS
    PASTA_RAW e o olist.duckdb são resolvidos a partir da localização deste
    arquivo (a pasta acima de pipeline/), nunca do diretório corrente.
    Por quê: rodar o script de outra pasta não pode criar um olist.duckdb
    vazio no lugar errado, que parece ingestão quebrada.

D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS
    Este módulo não lê CSV, não conhece nome de tabela, não imprime nada e
    não converte tipo. Quem decide tudo isso é cada etapa.
    Por quê: as aulas 2, 3 e 4 importam este arquivo. Uma regra de negócio
    escondida aqui valeria para todas as etapas sem aparecer em nenhuma spec.

D3. gravar
    Recria a tabela (CREATE OR REPLACE TABLE schema.tabela) com as colunas e
    os tipos do DataFrame, sem alterar nada: coluna str vira VARCHAR, nulo
    continua NULL. Não deixa view nem tabela temporária para trás.
    Devolve o SELECT count(*) da tabela recém-gravada, lido do banco.
    Por quê: a contagem que aparece na tela tem que ser a do que foi
    gravado, não a do que estava na memória.

D4. CONEXÃO
    conectar() devolve a conexão aberta; quem chama é quem fecha.
    Este módulo não guarda conexão global.
    Por quê: o .duckdb aceita um único processo escrevendo. Uma conexão
    esquecida aberta num módulo importado segura o lock sem ninguém ver.

Critérios de aceite:
- Importar pipeline.db não abre banco nem cria arquivo nenhum.
- conectar() chamado de dentro de outra pasta cria o olist.duckdb na raiz
  do projeto, e não na pasta corrente.
- gravar() com um DataFrame de 3 linhas devolve 3, e rodar duas vezes
  continua devolvendo 3.
"""

from pathlib import Path

import duckdb
import pandas as pd

PASTA_RAW = Path(__file__).resolve().parent.parent / "raw"


def conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(PASTA_RAW.parent / "olist.duckdb")


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    # No DuckDB 2.x todo execute() precisa ser consumido até o fim antes do
    # próximo comando na mesma conexão; complete() faz isso sem ler linhas.
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"').complete()


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    destino = f'"{schema}"."{tabela}"'
    # register cria uma view temporária apontando para o DataFrame; o finally
    # garante que ela some mesmo se o CREATE falhar (D3).
    temporaria = "__gravar_df"
    con.register(temporaria, df)
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {destino} AS SELECT * FROM {temporaria}"
        ).complete()
    finally:
        con.unregister(temporaria)
    # fetchall, não fetchone: só esvaziar o resultado libera a conexão.
    return con.execute(f"SELECT count(*) FROM {destino}").fetchall()[0][0]
