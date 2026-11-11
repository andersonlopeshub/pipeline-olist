"""Testes de pipeline/ingestao.py. Spec: docstring do módulo (itens 1 a 7).

Os nove .csv.gz são escritos pelo teste em tmp_path/raw, e o banco nasce em
tmp_path/olist.duckdb (db.PASTA_RAW aponta para tmp_path/raw).
"""

import gzip

import duckdb
import pytest

from pipeline import db, ingestao

PEDIDOS = (
    "order_id,order_status,order_purchase_timestamp\n"
    "p1,delivered,2017-01-05 10:00:00\n"  # pedido comum
    'p2,NA,\n'  # texto "NA" tem que continuar texto; data vazia vira nulo
    'p2,NA,\n'  # linha duplicada: a ingestão não descarta nada
)
CLIENTES = (
    "customer_id,customer_zip_code_prefix\n"
    "c1,01310\n"  # CEP com zero à esquerda: a inferência o perderia
)


def escrever_raw(pasta, sem=None):
    pasta.mkdir()
    for arquivo in ingestao.ARQUIVOS:
        if arquivo == sem:
            continue
        if arquivo == "olist_orders_dataset.csv.gz":
            texto = PEDIDOS
        elif arquivo == "olist_customers_dataset.csv.gz":
            texto = CLIENTES
        else:
            texto = "coluna\nvalor\n"  # uma linha qualquer: só precisa existir
        with gzip.open(pasta / arquivo, "wt", encoding="utf-8", newline="") as f:
            f.write(texto)


def preparar(tmp_path, monkeypatch, sem=None):
    raw = tmp_path / "raw"
    escrever_raw(raw, sem)
    monkeypatch.setattr(db, "PASTA_RAW", raw)
    monkeypatch.setattr(ingestao, "PASTA_RAW", raw)


def consultar(tmp_path, sql):
    con = duckdb.connect(tmp_path / "olist.duckdb", read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_csv_vira_tabela_com_as_mesmas_linhas(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    assert consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(3,)]
    assert consultar(tmp_path, "SELECT count(*) FROM raw.clientes") == [(1,)]
    assert consultar(tmp_path, "SELECT count(*) FROM raw.vendedores") == [(1,)]


def test_cada_arquivo_vira_a_tabela_do_mapa(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    tabelas = consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'raw' ORDER BY 1",
    )
    assert [t for (t,) in tabelas] == sorted(ingestao.ARQUIVOS.values())


def test_toda_coluna_entra_como_varchar(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    tipos = consultar(
        tmp_path,
        "SELECT DISTINCT data_type FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'pedidos'",
    )
    assert tipos == [("VARCHAR",)]


def test_cep_mantem_o_zero_a_esquerda(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    assert consultar(tmp_path, "SELECT customer_zip_code_prefix FROM raw.clientes") == [("01310",)]


def test_campo_vazio_vira_nulo_e_texto_na_continua_texto(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    linhas = consultar(
        tmp_path,
        "SELECT order_status, order_purchase_timestamp FROM raw.pedidos WHERE order_id = 'p2'",
    )
    assert linhas == [("NA", None), ("NA", None)]


def test_linha_duplicada_nao_e_descartada(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    assert consultar(tmp_path, "SELECT count(*) FROM raw.pedidos WHERE order_id = 'p2'") == [(2,)]


def test_data_continua_texto_sem_conversao(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    linhas = consultar(
        tmp_path, "SELECT order_purchase_timestamp FROM raw.pedidos WHERE order_id = 'p1'"
    )
    assert linhas == [("2017-01-05 10:00:00",)]


def test_rodar_duas_vezes_recria_e_nao_acrescenta(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    ingestao.main()
    ingestao.main()
    assert consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(3,)]


def test_arquivo_faltando_encerra_antes_de_abrir_o_banco(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, sem="olist_sellers_dataset.csv.gz")
    with pytest.raises(SystemExit) as saida:
        ingestao.main()
    assert saida.value.code == 1
    assert not (tmp_path / "olist.duckdb").exists()


def test_milhar_separa_com_ponto():
    assert ingestao.milhar(1550922) == "1.550.922"
    assert ingestao.milhar(999) == "999"
