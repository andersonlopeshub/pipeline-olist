"""Etapa 1 do pipeline Olist: ingestão dos nove .csv.gz no schema raw.

Execução:
    uv run python -m pipeline.ingestao

1. ESCOPO E NOMES
   Schema de destino: raw. Mapa arquivo -> tabela, completo e literal, em
   ARQUIVOS abaixo.
   Por quê: os nomes vão para o português porque é o vocabulário digitado de
   memória nos JOINs das próximas aulas.

2. PROIBIÇÕES (a regra central desta etapa)
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Data continua texto, nulo continua nulo.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined, na etapa 2. Se a correção acontecer aqui, a fronteira some.

3. REEXECUÇÃO
   Rodar dez vezes dá o mesmo resultado que rodar uma: cada tabela é
   recriada (CREATE OR REPLACE), nunca acrescentada.
   Por quê: é o que permite errar sem medo.

4. LEITURA DO ARQUIVO
   encoding declarado como utf-8, nunca adivinhado. Os .csv.gz são lidos
   direto, sem descompactar em disco. Campo vazio vira nulo, não string
   vazia.
   Por quê: encoding adivinhado muda de máquina para máquina, e o acento
   errado entraria no raw como se fosse o dado de origem.

5. TIPAGEM
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Por quê: a inferência lê CEP com zero à esquerda como número e o zero
   desaparece sem aviso. A conversão acontece na etapa 2, onde é uma decisão
   registrada.

6. SAÍDA NA TELA
   Uma linha por tabela, com nome qualificado e contagem vinda do banco (não
   do DataFrame), milhar separado por ponto, e uma linha final com o total.
   stdout reconfigurado para utf-8.
   Por quê: essa saída é o único instrumento de conferência desta etapa. E o
   Prompt de Comando do Windows embaralha acento por padrão.

7. ERRO
   Antes de abrir o banco, verifica se os nove arquivos existem. Faltando
   qualquer um: lista os que faltam, diz em que pasta procurou e encerra com
   sys.exit(1), sem ingerir nada.
   Por quê: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo.

Critérios de aceite:
- A execução imprime nove linhas e um total de 1.550.922 registros.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- SELECT * FROM raw.pedidos devolve todas as colunas como VARCHAR.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer
  tabela.
- O script termina sozinho e devolve o terminal: nenhum processo fica de pé.
"""

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"

ARQUIVOS = {
    "olist_orders_dataset.csv.gz": "pedidos",
    "olist_order_items_dataset.csv.gz": "itens_pedido",
    "olist_order_payments_dataset.csv.gz": "pagamentos",
    "olist_order_reviews_dataset.csv.gz": "avaliacoes",
    "olist_customers_dataset.csv.gz": "clientes",
    "olist_sellers_dataset.csv.gz": "vendedores",
    "olist_products_dataset.csv.gz": "produtos",
    "product_category_name_translation.csv.gz": "traducao_categorias",
    "olist_geolocation_dataset.csv.gz": "geolocalizacao",
}


def ler(nome_arquivo: str) -> pd.DataFrame:
    return pd.read_csv(
        PASTA_RAW / nome_arquivo,
        dtype=str,
        encoding="utf-8",
        compression="gzip",
        # Por padrão o pandas também transforma em nulo textos como "NA",
        # "null", "None" e "n/a". Isso seria corrigir valor (item 2): só o
        # campo vazio vira nulo.
        keep_default_na=False,
        na_values=[""],
    )


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    faltando = [a for a in ARQUIVOS if not (PASTA_RAW / a).is_file()]
    if faltando:
        print(f"Arquivos não encontrados em {PASTA_RAW}:", file=sys.stderr)
        for nome in faltando:
            print(f"  {nome}", file=sys.stderr)
        print("Nada foi ingerido.", file=sys.stderr)
        sys.exit(1)

    largura = max(len(f"{SCHEMA}.{t}") for t in ARQUIVOS.values())
    total = 0
    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        for arquivo, tabela in ARQUIVOS.items():
            linhas = gravar(con, ler(arquivo), SCHEMA, tabela)
            total += linhas
            nome = f"{SCHEMA}.{tabela}"
            print(f"{nome:<{largura}}  {milhar(linhas):>9}")
    finally:
        con.close()
    print(f"{'Total':<{largura}}  {milhar(total):>9}")


if __name__ == "__main__":    main()
