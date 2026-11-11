"""Testes de pipeline/marts.py (M1 a M4) e de dois .sql de sql/marts/.

O banco nasce em tmp_path/olist.duckdb, com as nove tabelas de refined
inventadas pelo teste. Os .sql de teste ficam em tmp_path/sql (PASTA_SQL).
"""

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from pipeline import db, marts

SQL_DO_PROJETO = Path(__file__).resolve().parent.parent / "sql" / "marts"


# --- Montagem -----------------------------------------------------------------


def criar_refined(caminho):
    con = duckdb.connect(caminho)
    con.execute("CREATE SCHEMA refined").complete()
    for tabela in marts.TABELAS_ORIGEM:
        con.execute(f'CREATE TABLE refined."{tabela}" (order_id VARCHAR)').complete()
    # Dois pedidos: dão um mart com linhas e um filtro que não casa nada.
    con.execute("INSERT INTO refined.pedidos VALUES ('p1'), ('p2')").complete()
    con.close()


def preparar(tmp_path, monkeypatch, arquivos):
    (tmp_path / "raw").mkdir()
    pasta = tmp_path / "sql"
    pasta.mkdir()
    monkeypatch.setattr(db, "PASTA_RAW", tmp_path / "raw")
    monkeypatch.setattr(marts, "PASTA_SQL", pasta)
    criar_refined(tmp_path / "olist.duckdb")
    escrever(pasta, arquivos)
    return pasta


def escrever(pasta, arquivos):
    for nome, sql in arquivos.items():
        (pasta / nome).write_text(sql, encoding="utf-8")


def consultar(tmp_path, sql):
    con = duckdb.connect(tmp_path / "olist.duckdb", read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def tabelas_marts(tmp_path):
    linhas = consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'marts' ORDER BY 1",
    )
    return [t for (t,) in linhas]


def espiar_criar_marts(monkeypatch):
    chamadas = []
    monkeypatch.setattr(marts, "criar_marts", lambda *a: chamadas.append(a))
    return chamadas


# --- pipeline/marts.py ----------------------------------------------------------


def test_cada_arquivo_vira_uma_tabela_sem_o_prefixo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    marts.main()
    assert tabelas_marts(tmp_path) == ["teste"]
    assert consultar(tmp_path, "SELECT x FROM marts.teste") == [(1,)]


def test_mart_le_de_refined(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"01_pedidos.sql": "SELECT order_id FROM refined.pedidos"})
    marts.main()
    assert consultar(tmp_path, "SELECT count(*) FROM marts.pedidos") == [(2,)]


def test_arquivo_apagado_faz_o_mart_sumir_na_execucao_seguinte(tmp_path, monkeypatch):
    pasta = preparar(
        tmp_path, monkeypatch, {"01_fica.sql": "SELECT 1 AS x", "02_sai.sql": "SELECT 2 AS x"}
    )
    marts.main()
    (pasta / "02_sai.sql").unlink()
    marts.main()
    assert tabelas_marts(tmp_path) == ["fica"]


def test_rodar_duas_vezes_da_o_mesmo_resultado(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"01_pedidos.sql": "SELECT order_id FROM refined.pedidos"})
    marts.main()
    marts.main()
    assert consultar(tmp_path, "SELECT count(*) FROM marts.pedidos") == [(2,)]


def test_arquivo_sem_prefixo_para_antes_de_executar_qualquer_sql(tmp_path, monkeypatch):
    # 01_ok.sql é válido; teste.sql, sem NN_, tem que barrar os dois.
    preparar(tmp_path, monkeypatch, {"01_ok.sql": "SELECT 1 AS x", "teste.sql": "SELECT 1 AS x"})
    chamadas = espiar_criar_marts(monkeypatch)
    with pytest.raises(SystemExit):
        marts.main()
    assert chamadas == []
    assert tabelas_marts(tmp_path) == []


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param_antes_de_executar(tmp_path, monkeypatch):
    # O DuckDB não diferencia maiúscula: os dois virariam marts.vendas.
    preparar(tmp_path, monkeypatch, {"01_Vendas.sql": "SELECT 1 AS x", "02_vendas.sql": "SELECT 2 AS x"})
    chamadas = espiar_criar_marts(monkeypatch)
    with pytest.raises(SystemExit):
        marts.main()
    assert chamadas == []


def test_mart_vazio_encerra_e_deixa_o_schema_marts_como_estava(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch, {"01_a.sql": "SELECT 1 AS x"})
    marts.main()
    # Segunda execução: 01_a mudaria para 2, mas 02_vazio não devolve linha.
    escrever(pasta, {"01_a.sql": "SELECT 2 AS x", "02_vazio.sql": "SELECT 1 AS x WHERE false"})
    with pytest.raises(SystemExit):
        marts.main()
    assert tabelas_marts(tmp_path) == ["a"]
    assert consultar(tmp_path, "SELECT x FROM marts.a") == [(1,)]


def test_sql_com_erro_encerra_e_deixa_o_schema_marts_como_estava(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch, {"01_a.sql": "SELECT 1 AS x"})
    marts.main()
    escrever(pasta, {"02_quebrado.sql": "SELEC 1"})  # erro de sintaxe
    with pytest.raises(SystemExit):
        marts.main()
    assert tabelas_marts(tmp_path) == ["a"]


def test_arquivo_com_dois_comandos_e_recusado_sem_executar_o_segundo(tmp_path, monkeypatch):
    # O DROP depois do SELECT apagaria refined se fosse executado.
    preparar(tmp_path, monkeypatch, {"01_a.sql": "SELECT 1 AS x; DROP TABLE refined.pedidos"})
    with pytest.raises(SystemExit):
        marts.main()
    assert consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(2,)]


def test_pasta_sem_sql_encerra_sem_apagar_marts(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch, {"01_a.sql": "SELECT 1 AS x"})
    marts.main()
    (pasta / "01_a.sql").unlink()
    with pytest.raises(SystemExit):
        marts.main()
    assert tabelas_marts(tmp_path) == ["a"]


def test_refined_faltando_encerra_sem_criar_marts(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"01_a.sql": "SELECT 1 AS x"})
    con = duckdb.connect(tmp_path / "olist.duckdb")
    con.execute("DROP TABLE refined.vendedores").complete()
    con.close()
    with pytest.raises(SystemExit):
        marts.main()
    assert tabelas_marts(tmp_path) == []


def test_ler_sql_tira_bom_espacos_e_um_ponto_e_virgula(tmp_path):
    arquivo = tmp_path / "01_a.sql"
    # BOM que editores do Windows gravam, mais ";" e quebra de linha no fim.
    arquivo.write_text("SELECT 1 AS x;\n\n", encoding="utf-8-sig")
    assert marts.ler_sql(arquivo) == "SELECT 1 AS x"


def test_milhar_separa_com_ponto():
    assert marts.milhar(3053) == "3.053"


# --- sql/marts/01 e 03 sobre tabelas inventadas -------------------------------


def rodar_sql_do_projeto(con, arquivo):
    return con.execute(marts.ler_sql(SQL_DO_PROJETO / arquivo)).fetchall()


def banco_vendas(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    con.execute("CREATE SCHEMA refined").complete()
    con.execute(
        "CREATE TABLE refined.pedidos (order_id VARCHAR, order_status VARCHAR, "
        "order_purchase_timestamp TIMESTAMP)"
    ).complete()
    con.execute(
        "CREATE TABLE refined.itens_pedido (order_id VARCHAR, order_item_id INTEGER, "
        "price DECIMAL(10,2))"
    ).complete()
    con.execute(
        """INSERT INTO refined.pedidos VALUES
        ('p1', 'delivered',   '2017-03-10 10:00:00'),  -- pedido com dois itens
        ('p2', 'canceled',    '2017-03-15 11:00:00'),  -- cancelado: fora
        ('p3', 'unavailable', '2017-03-20 12:00:00'),  -- indisponível: fora
        ('p4', 'shipped',     '2017-04-02 09:00:00')   -- outro mês, ainda em trânsito
        """
    ).complete()
    con.execute(
        """INSERT INTO refined.itens_pedido VALUES
        ('p1', 1, 10.00),
        ('p1', 2, 20.00),
        ('p2', 1, 100.00),
        ('p3', 1, 50.00),
        ('p4', 1, 5.50)
        """
    ).complete()
    return con


def test_pedido_com_dois_itens_conta_uma_vez(tmp_path):
    con = banco_vendas(tmp_path)
    linhas = rodar_sql_do_projeto(con, "01_vendas_mensais.sql")
    con.close()
    marco = linhas[0]
    # p1 é o único pedido válido de março: 1 pedido, 10,00 + 20,00 de receita.
    assert marco[1] == 1
    assert marco[2] == Decimal("30.00")


def test_cancelado_fica_fora_da_receita(tmp_path):
    con = banco_vendas(tmp_path)
    linhas = rodar_sql_do_projeto(con, "01_vendas_mensais.sql")
    con.close()
    # Sem p2 (100,00) e p3 (50,00): março fica só com os 30,00 de p1.
    assert [(str(mes), receita) for mes, _, receita in linhas] == [
        ("2017-03-01", Decimal("30.00")),
        ("2017-04-01", Decimal("5.50")),
    ]


def banco_entregas(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    con.execute("CREATE SCHEMA refined").complete()
    con.execute(
        "CREATE TABLE refined.pedidos (order_id VARCHAR, order_status VARCHAR, "
        "order_delivered_customer_date TIMESTAMP, order_estimated_delivery_date DATE)"
    ).complete()
    con.execute(
        """INSERT INTO refined.pedidos VALUES
        ('e1', 'delivered', '2017-05-10 15:00:00', '2017-05-10'),  -- no dia previsto, às 15h
        ('e2', 'delivered', '2017-05-09 08:00:00', '2017-05-10'),  -- um dia antes
        ('e3', 'delivered', '2017-05-11 09:00:00', '2017-05-10'),  -- dia seguinte, de manhã: atrasado
        ('e4', 'delivered', NULL,                  '2017-05-10'),  -- entregue sem data: fora
        ('e5', 'canceled',  '2017-05-01 10:00:00', '2017-05-10')   -- não é delivered: fora
        """
    ).complete()
    return con


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path):
    con = banco_entregas(tmp_path)
    entregues, no_prazo, atrasados, pct = rodar_sql_do_projeto(con, "03_entrega_no_prazo.sql")[0]
    con.close()
    # e1 e e2 no prazo, e3 atrasado; e4 e e5 não contam.
    assert (entregues, no_prazo, atrasados) == (3, 2, 1)
    # 100 * 2 / 3 = 66,666... arredondado a uma casa.
    assert pct == 66.7
