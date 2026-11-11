"""Etapa 2 do pipeline Olist: passagem de raw para refined.

Execução:
    uv run python -m pipeline.refinamento

Spec (fonte da verdade): specs/transformacao.md
"""

import sys

from pipeline.db import conectar, criar_schema

ORIGEM = "raw"
DESTINO = "refined"

REGEX_INTEIRO = r"^-?\d+$"
REGEX_DINHEIRO = r"^-?\d+(\.\d{1,2})?$"

# tabela -> chave (lista ou None) e colunas (nome_raw, nome_refined, tipo)
TABELAS = {
    "pedidos": {
        "chave": ["order_id"],
        "colunas": [
            ("order_id", "order_id", "VARCHAR"),
            ("customer_id", "customer_id", "VARCHAR"),
            ("order_status", "order_status", "VARCHAR"),
            ("order_purchase_timestamp", "order_purchase_timestamp", "TIMESTAMP"),
            ("order_approved_at", "order_approved_at", "TIMESTAMP"),
            ("order_delivered_carrier_date", "order_delivered_carrier_date", "TIMESTAMP"),
            ("order_delivered_customer_date", "order_delivered_customer_date", "TIMESTAMP"),
            ("order_estimated_delivery_date", "order_estimated_delivery_date", "DATE"),
        ],
    },
    "itens_pedido": {
        "chave": ["order_id", "order_item_id"],
        "colunas": [
            ("order_id", "order_id", "VARCHAR"),
            ("order_item_id", "order_item_id", "INTEGER"),
            ("product_id", "product_id", "VARCHAR"),
            ("seller_id", "seller_id", "VARCHAR"),
            ("shipping_limit_date", "shipping_limit_date", "TIMESTAMP"),
            ("price", "price", "DECIMAL(10,2)"),
            ("freight_value", "freight_value", "DECIMAL(10,2)"),
        ],
    },
    "pagamentos": {
        "chave": ["order_id", "payment_sequential"],
        "colunas": [
            ("order_id", "order_id", "VARCHAR"),
            ("payment_sequential", "payment_sequential", "INTEGER"),
            ("payment_type", "payment_type", "VARCHAR"),
            ("payment_installments", "payment_installments", "INTEGER"),
            ("payment_value", "payment_value", "DECIMAL(10,2)"),
        ],
    },
    "avaliacoes": {
        "chave": ["review_id", "order_id"],
        "colunas": [
            ("review_id", "review_id", "VARCHAR"),
            ("order_id", "order_id", "VARCHAR"),
            ("review_score", "review_score", "INTEGER"),
            ("review_comment_title", "review_comment_title", "VARCHAR"),
            ("review_comment_message", "review_comment_message", "VARCHAR"),
            ("review_creation_date", "review_creation_date", "TIMESTAMP"),
            ("review_answer_timestamp", "review_answer_timestamp", "TIMESTAMP"),
        ],
    },
    "clientes": {
        "chave": ["customer_id"],
        "colunas": [
            ("customer_id", "customer_id", "VARCHAR"),
            ("customer_unique_id", "customer_unique_id", "VARCHAR"),
            ("customer_zip_code_prefix", "customer_zip_code_prefix", "VARCHAR"),
            ("customer_city", "customer_city", "VARCHAR"),
            ("customer_state", "customer_state", "VARCHAR"),
        ],
    },
    "vendedores": {
        "chave": ["seller_id"],
        "colunas": [
            ("seller_id", "seller_id", "VARCHAR"),
            ("seller_zip_code_prefix", "seller_zip_code_prefix", "VARCHAR"),
            ("seller_city", "seller_city", "VARCHAR"),
            ("seller_state", "seller_state", "VARCHAR"),
        ],
    },
    "produtos": {
        "chave": ["product_id"],
        "colunas": [
            ("product_id", "product_id", "VARCHAR"),
            ("product_category_name", "product_category_name", "VARCHAR"),
            ("product_name_lenght", "product_name_length", "INTEGER"),
            ("product_description_lenght", "product_description_length", "INTEGER"),
            ("product_photos_qty", "product_photos_qty", "INTEGER"),
            ("product_weight_g", "product_weight_g", "INTEGER"),
            ("product_length_cm", "product_length_cm", "INTEGER"),
            ("product_height_cm", "product_height_cm", "INTEGER"),
            ("product_width_cm", "product_width_cm", "INTEGER"),
        ],
    },
    "traducao_categorias": {
        "chave": ["product_category_name"],
        "colunas": [
            ("product_category_name", "product_category_name", "VARCHAR"),
            ("product_category_name_english", "product_category_name_english", "VARCHAR"),
        ],
    },
    "geolocalizacao": {
        "chave": None,
        "colunas": [
            ("geolocation_zip_code_prefix", "geolocation_zip_code_prefix", "VARCHAR"),
            ("geolocation_lat", "geolocation_lat", "DOUBLE"),
            ("geolocation_lng", "geolocation_lng", "DOUBLE"),
            ("geolocation_city", "geolocation_city", "VARCHAR"),
            ("geolocation_state", "geolocation_state", "VARCHAR"),
        ],
    },
}


def condicao_falha(coluna: str, tipo: str) -> str | None:
    """SQL que é verdadeiro para os valores que NÃO convertem."""
    c = f'"{coluna}"'
    if tipo == "VARCHAR":
        return None
    if tipo == "INTEGER":
        return f"{c} IS NOT NULL AND NOT regexp_matches({c}, '{REGEX_INTEIRO}')"
    if tipo == "DECIMAL(10,2)":
        return f"{c} IS NOT NULL AND NOT regexp_matches({c}, '{REGEX_DINHEIRO}')"
    if tipo == "DOUBLE":
        return f"{c} IS NOT NULL AND TRY_CAST({c} AS DOUBLE) IS NULL"
    if tipo == "TIMESTAMP":
        return f"{c} IS NOT NULL AND TRY_CAST({c} AS TIMESTAMP) IS NULL"
    if tipo == "DATE":
        # DATE só aceita valor à meia-noite; hora diferente seria perdida.
        ts = f"TRY_CAST({c} AS TIMESTAMP)"
        return (
            f"{c} IS NOT NULL AND ({ts} IS NULL "
            f"OR {ts} <> date_trunc('day', {ts}))"
        )
    raise ValueError(f"tipo não previsto: {tipo}")


def expressao_select(coluna: str, tipo: str) -> str:
    c = f'"{coluna}"'
    if tipo == "VARCHAR":
        return c
    if tipo == "DATE":
        return f"CAST(CAST({c} AS TIMESTAMP) AS DATE)"
    return f"CAST({c} AS {tipo})"


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def colunas_existentes(con) -> dict[str, set[str]]:
    linhas = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = ?",
        [ORIGEM],
    ).fetchall()
    mapa: dict[str, set[str]] = {}
    for tabela, coluna in linhas:
        mapa.setdefault(tabela, set()).add(coluna)
    return mapa


def validar(con) -> list[str]:
    """Confere colunas e conversões de todas as tabelas. Não grava nada."""
    erros = []
    existentes = colunas_existentes(con)
    for tabela, spec in TABELAS.items():
        for raw, _, tipo in spec["colunas"]:
            if raw not in existentes.get(tabela, set()):
                erros.append(f"{ORIGEM}.{tabela}.{raw}: coluna ausente")
                continue
            cond = condicao_falha(raw, tipo)
            if cond is None:
                continue
            total = con.execute(
                f'SELECT count(*) FROM {ORIGEM}."{tabela}" WHERE {cond}'
            ).fetchone()[0]
            if total:
                exemplos = con.execute(
                    f'SELECT DISTINCT "{raw}" FROM {ORIGEM}."{tabela}" '
                    f"WHERE {cond} LIMIT 5"
                ).fetchall()
                lista = ", ".join(repr(e[0]) for e in exemplos)
                erros.append(
                    f"{ORIGEM}.{tabela}.{raw} -> {tipo}: "
                    f"{milhar(total)} valores não convertem. Exemplos: {lista}"
                )
    return erros


def relatorio_chave(con, tabela: str, spec: dict, colunas: list[str]) -> None:
    origem = f'{ORIGEM}."{tabela}"'
    chave = spec["chave"]
    todas = ", ".join(f'coalesce(CAST("{c}" AS VARCHAR), \'<NULL>\')' for c in colunas)
    linha_md5 = f"md5(concat_ws(chr(31), {todas}))"

    if chave is None:
        exatas = con.execute(
            f"SELECT count(*) - count(DISTINCT {linha_md5}) FROM {origem}"
        ).fetchone()[0]
        print(f"  chave: nenhuma | linhas exatamente repetidas: {milhar(exatas)} (mantidas)")
        return

    lista = ", ".join(f'"{c}"' for c in chave)
    grupos = con.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {origem} GROUP BY {lista} "
        f"HAVING count(*) > 1)"
    ).fetchone()[0]
    conflitantes = con.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {origem} GROUP BY {lista} "
        f"HAVING count(DISTINCT {linha_md5}) > 1)"
    ).fetchone()[0]
    print(
        f"  chave: {', '.join(chave)} | chaves repetidas: {milhar(grupos)} "
        f"(conteúdo diferente: {milhar(conflitantes)}, "
        f"idêntico: {milhar(grupos - conflitantes)}) (mantidas)"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        existentes = colunas_existentes(con)
        faltando = [t for t in TABELAS if t not in existentes]
        if faltando:
            print(f"Tabelas faltando em {ORIGEM}:", file=sys.stderr)
            for t in faltando:
                print(f"  {ORIGEM}.{t}", file=sys.stderr)
            print(
                "Rode a ingestão antes: uv run python -m pipeline.ingestao",
                file=sys.stderr,
            )
            sys.exit(1)

        erros = validar(con)
        if erros:
            print("Conversão falhou. Nada foi gravado em refined:", file=sys.stderr)
            for e in erros:
                print(f"  {e}", file=sys.stderr)
            sys.exit(1)

        criar_schema(con, DESTINO)
        largura = max(len(f"{DESTINO}.{t}") for t in TABELAS)
        total = 0
        for tabela, spec in TABELAS.items():
            colunas_ref = [ref for _, ref, _ in spec["colunas"]]
            colunas_raw = [raw for raw, _, _ in spec["colunas"]]
            print(f"\n{DESTINO}.{tabela}")
            # o relatório consulta a tabela raw, então usa os nomes raw
            relatorio_chave(con, tabela, spec, colunas_raw)

            select = ", ".join(
                f"{expressao_select(raw, tipo)} AS \"{ref}\""
                for raw, ref, tipo in spec["colunas"]
            )
            con.execute(
                f'CREATE OR REPLACE TABLE {DESTINO}."{tabela}" AS '
                f'SELECT {select} FROM {ORIGEM}."{tabela}"'
            ).complete()

            linhas = con.execute(
                f'SELECT count(*) FROM {DESTINO}."{tabela}"'
            ).fetchone()[0]
            total += linhas
            print(f"  linhas: {milhar(linhas)}")

            nulos = []
            for ref in colunas_ref:
                n = con.execute(
                    f'SELECT count(*) FROM {DESTINO}."{tabela}" WHERE "{ref}" IS NULL'
                ).fetchone()[0]
                if n:
                    nulos.append(f"{ref} {milhar(n)}")
            if nulos:
                print(f"  nulos: {', '.join(nulos)}")

        print(f"\n{'Total':<{largura}}  {milhar(total):>9}")
    finally:
        con.close()

if __name__ == "__main__":    main()
