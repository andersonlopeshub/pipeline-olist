"""Testes da etapa 2, raw -> refined.

O módulo é pipeline/refinamento.py (não existe pipeline/transformacao.py); a
spec é specs/transformacao.md. O teste monta as nove tabelas de raw, todas
VARCHAR como a ingestão grava, em tmp_path/olist.duckdb.
"""

import duckdb
import pytest

from pipeline import db, refinamento


def criar_raw(caminho, linhas, sem_tabela=None, sem_coluna=None):
    """Cria raw.<tabela> com as colunas de TABELAS, todas VARCHAR.

    linhas: tabela -> lista de dicts; coluna ausente no dict entra NULL.
    """
    con = duckdb.connect(caminho)
    con.execute("CREATE SCHEMA raw").complete()
    for tabela, spec in refinamento.TABELAS.items():
        if tabela == sem_tabela:
            continue
        colunas = [raw for raw, _, _ in spec["colunas"] if raw != sem_coluna]
        definicao = ", ".join(f'"{c}" VARCHAR' for c in colunas)
        con.execute(f'CREATE TABLE raw."{tabela}" ({definicao})').complete()
        for linha in linhas.get(tabela, []):
            valores = [linha.get(c) for c in colunas]
            marcas = ", ".join("?" for _ in colunas)
            con.execute(f'INSERT INTO raw."{tabela}" VALUES ({marcas})', valores).complete()
    con.close()


def pedido(order_id, **extra):
    base = {
        "order_id": order_id,
        "customer_id": "c1",
        "order_status": "delivered",
        "order_purchase_timestamp": "2017-03-10 10:15:00",
        "order_estimated_delivery_date": "2017-03-20 00:00:00",
    }
    return {**base, **extra}


LINHAS_BOAS = {
    "pedidos": [
        pedido("p1"),  # pedido completo
        pedido("p2", order_delivered_customer_date=None),  # data nula continua nula
        pedido("p3"),  # p3 duas vezes, idêntico: duplicata exata
        pedido("p3"),
    ],
    "itens_pedido": [
        {"order_id": "p1", "order_item_id": "1", "price": "10.5", "freight_value": "2.00"},
    ],
    "produtos": [
        # colunas com o erro de digitação "lenght" da origem
        {"product_id": "x", "product_name_lenght": "40", "product_description_lenght": "300"},
    ],
    "geolocalizacao": [
        {"geolocation_zip_code_prefix": "01310", "geolocation_lat": "-23.56", "geolocation_lng": "-46.65"},
    ],
}


def preparar(tmp_path, monkeypatch, linhas=LINHAS_BOAS, **criar):
    (tmp_path / "raw").mkdir()
    monkeypatch.setattr(db, "PASTA_RAW", tmp_path / "raw")
    criar_raw(tmp_path / "olist.duckdb", linhas, **criar)


def consultar(tmp_path, sql):
    con = duckdb.connect(tmp_path / "olist.duckdb", read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def tipo(tmp_path, tabela, coluna):
    return consultar(
        tmp_path,
        "SELECT data_type FROM information_schema.columns WHERE table_schema = 'refined' "
        f"AND table_name = '{tabela}' AND column_name = '{coluna}'",
    )[0][0]


def tabelas_refined(tmp_path):
    return consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'refined'",
    )[0][0]


def com(tabela, linha):
    """LINHAS_BOAS com uma linha a mais em uma tabela."""
    return {**LINHAS_BOAS, tabela: LINHAS_BOAS.get(tabela, []) + [linha]}


def test_as_nove_tabelas_aparecem_em_refined(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    assert tabelas_refined(tmp_path) == 9


def test_datas_viram_timestamp_e_dinheiro_decimal(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    assert tipo(tmp_path, "pedidos", "order_purchase_timestamp") == "TIMESTAMP"
    assert tipo(tmp_path, "pedidos", "order_estimated_delivery_date") == "DATE"
    assert tipo(tmp_path, "itens_pedido", "price") == "DECIMAL(10,2)"
    assert tipo(tmp_path, "itens_pedido", "order_item_id") == "INTEGER"
    assert tipo(tmp_path, "geolocalizacao", "geolocation_lat") == "DOUBLE"
    assert tipo(tmp_path, "geolocalizacao", "geolocation_zip_code_prefix") == "VARCHAR"


def test_dinheiro_com_uma_casa_vira_decimal_exato(tmp_path, monkeypatch):
    from decimal import Decimal

    preparar(tmp_path, monkeypatch)
    refinamento.main()
    assert consultar(tmp_path, "SELECT price FROM refined.itens_pedido") == [(Decimal("10.50"),)]


def test_cep_continua_texto_com_zero_a_esquerda(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    linhas = consultar(tmp_path, "SELECT geolocation_zip_code_prefix FROM refined.geolocalizacao")
    assert linhas == [("01310",)]


def test_colunas_lenght_sao_renomeadas_para_length(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    linhas = consultar(
        tmp_path, "SELECT product_name_length, product_description_length FROM refined.produtos"
    )
    assert linhas == [(40, 300)]


def test_nulo_continua_nulo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    linhas = consultar(
        tmp_path,
        "SELECT order_delivered_customer_date FROM refined.pedidos WHERE order_id = 'p2'",
    )
    assert linhas == [(None,)]


def test_duplicata_exata_continua_em_refined(tmp_path, monkeypatch):
    # Regra atual da spec (item 4): duplicata só entra no relatório.
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    assert consultar(tmp_path, "SELECT count(*) FROM refined.pedidos WHERE order_id = 'p3'") == [(2,)]


def test_nenhuma_linha_se_perde_entre_raw_e_refined(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    for tabela in refinamento.TABELAS:
        raw = consultar(tmp_path, f'SELECT count(*) FROM raw."{tabela}"')
        refined = consultar(tmp_path, f'SELECT count(*) FROM refined."{tabela}"')
        assert raw == refined, tabela


def test_rodar_duas_vezes_nao_acrescenta_linhas(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    refinamento.main()
    refinamento.main()
    assert consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(4,)]


def test_dinheiro_com_virgula_encerra_sem_gravar_nada(tmp_path, monkeypatch):
    # "12,50": vírgula decimal não converte para DECIMAL.
    linha = {"order_id": "p9", "order_item_id": "1", "price": "12,50"}
    preparar(tmp_path, monkeypatch, linhas=com("itens_pedido", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_dinheiro_com_tres_casas_encerra_em_vez_de_arredondar(tmp_path, monkeypatch):
    linha = {"order_id": "p9", "order_item_id": "1", "price": "10.005"}
    preparar(tmp_path, monkeypatch, linhas=com("itens_pedido", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_inteiro_com_casa_decimal_encerra(tmp_path, monkeypatch):
    linha = {"review_id": "r1", "order_id": "p1", "review_score": "4.5"}
    preparar(tmp_path, monkeypatch, linhas=com("avaliacoes", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_data_invalida_encerra_em_vez_de_virar_nulo(tmp_path, monkeypatch):
    linha = pedido("p9", order_purchase_timestamp="31/02/2017")
    preparar(tmp_path, monkeypatch, linhas=com("pedidos", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_data_prevista_com_hora_encerra_em_vez_de_perder_a_hora(tmp_path, monkeypatch):
    linha = pedido("p9", order_estimated_delivery_date="2017-03-20 15:00:00")
    preparar(tmp_path, monkeypatch, linhas=com("pedidos", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_coordenada_que_nao_e_numero_encerra(tmp_path, monkeypatch):
    linha = {"geolocation_zip_code_prefix": "1", "geolocation_lat": "abc"}
    preparar(tmp_path, monkeypatch, linhas=com("geolocalizacao", linha))
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_tabela_faltando_em_raw_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, sem_tabela="vendedores")
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_coluna_faltando_em_raw_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, sem_coluna="seller_city")
    with pytest.raises(SystemExit):
        refinamento.main()
    assert tabelas_refined(tmp_path) == 0


def test_tipo_nao_previsto_levanta_erro():
    with pytest.raises(ValueError):
        refinamento.condicao_falha("x", "BLOB")
