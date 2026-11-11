"""Testes de painel.py: leitura (P1), cartões (P3), formato e gráficos (P4).

ler() abre "olist.duckdb" relativo à pasta corrente: o teste faz chdir para
tmp_path e cria lá um banco com marts inventados.
"""

import duckdb
import pandas as pd
import pytest

import painel


# --- P4. Formato ----------------------------------------------------------------


def test_reais_usa_ponto_no_milhar_e_virgula_no_decimal():
    assert painel.reais(1234567.89) == "R$ 1.234.567,89"


def test_reais_completa_as_casas_decimais():
    assert painel.reais(5) == "R$ 5,00"
    assert painel.reais(0) == "R$ 0,00"


def test_reais_aceita_outra_quantidade_de_casas():
    assert painel.reais(1500, 0) == "R$ 1.500"


def test_pct_tem_uma_casa_por_padrao():
    assert painel.pct(12.34) == "12,3%"


def test_pct_aceita_duas_casas():
    assert painel.pct(0.5, 2) == "0,50%"


def test_numero_sem_casas_separa_o_milhar():
    assert painel.numero(1234567) == "1.234.567"


def test_numero_com_casas_e_negativo():
    assert painel.numero(-1234.5, 1) == "-1.234,5"


def test_numero_abaixo_de_mil_nao_ganha_ponto():
    assert painel.numero(999) == "999"


def test_mes_curto_usa_nome_em_portugues():
    assert painel.mes_curto(pd.Timestamp("2018-02-01")) == "fev/2018"
    assert painel.mes_curto(pd.Timestamp("2017-12-01")) == "dez/2017"


# --- P3. Cartões -----------------------------------------------------------------


def dados_cartoes():
    return {
        "kpis": pd.DataFrame(
            {
                "ticket_medio": [150.5],
                "pct_cancelados": [1.25],
                "pct_frete": [12.0],
                "dias_entrega": [9.5],
                "nota_media": [4.2],
            }
        ),
        "recompra": pd.DataFrame(
            {
                # A linha 2 vem antes de propósito: o cartão tem que achar a
                # linha 1 pelo valor, não pela posição.
                "pedidos_por_cliente": [2, 1],
                "pct_clientes": [10.0, 90.0],
            }
        ),
        "entrega_no_prazo": pd.DataFrame({"pct_no_prazo": [88.8]}),
    }


def test_sete_cartoes_na_ordem_da_spec():
    rotulos = [r for r, _ in painel.cartoes(dados_cartoes())]
    nomes = [r.split(" · ")[0] for r in rotulos]
    assert nomes == [
        "Ticket médio",
        "Cancelados",
        "Peso do frete",
        "Recompra",
        "No prazo",
        "Dias até entregar",
        "Nota média",
    ]


def test_cartoes_formatam_cada_valor_com_as_casas_da_spec():
    valores = [v for _, v in painel.cartoes(dados_cartoes())]
    assert valores == ["R$ 150,50", "1,25%", "12,0%", "10,00%", "88,8%", "9,5", "4,20"]


def test_recompra_e_o_complemento_de_quem_comprou_uma_vez():
    # 90% compraram uma vez só: recompra = 100 - 90 = 10.
    valores = dict(painel.cartoes(dados_cartoes()))
    assert valores["Recompra · % de clientes com 2+ pedidos"] == "10,00%"


# --- P1. Leitura -------------------------------------------------------------------


def criar_banco(pasta):
    con = duckdb.connect(pasta / "olist.duckdb")
    con.execute("CREATE SCHEMA marts").complete()
    # Duas linhas inventadas, para conferir que vêm todas.
    con.execute("CREATE TABLE marts.kpis AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) t(n, s)").complete()
    con.close()


def test_ler_devolve_cada_mart_com_todas_as_linhas_e_colunas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path)
    dados = painel.ler(["kpis"])
    assert list(dados) == ["kpis"]
    assert dados["kpis"].to_dict("list") == {"n": [1, 2], "s": ["a", "b"]}


def test_ler_deixa_de_fora_o_mart_que_nao_existe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path)
    dados = painel.ler(["kpis", "nao_existe"])
    assert list(dados) == ["kpis"]


def test_ler_deixa_de_fora_o_mart_com_nome_de_funcao_do_painel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path)
    # Os três marts que têm o nome de uma função de painel.py.
    dados = painel.ler(["kpis", "mix_pagamento", "clientes_por_uf", "nota_por_categoria"])
    assert list(dados) == ["kpis"]


def test_ler_nao_le_dataframe_python_com_o_nome_do_mart_que_falta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path)
    # DataFrame com o nome do mart nos globais de painel.py, que é onde o
    # replacement scan procura: o DuckDB não pode lê-lo no lugar do mart.
    monkeypatch.setattr(painel, "impostor", pd.DataFrame({"x": [999]}), raising=False)
    assert painel.ler(["impostor"]) == {}


def test_ler_sem_banco_levanta_file_not_found_e_nao_cria_arquivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        painel.ler(["kpis"])
    assert list(tmp_path.iterdir()) == []


def test_ler_fecha_a_conexao_e_libera_o_arquivo_para_gravar(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path)
    painel.ler(["kpis"])
    # Com uma conexão read_only ainda aberta no processo, o DuckDB recusaria
    # abrir o mesmo arquivo para escrita.
    con = duckdb.connect(tmp_path / "olist.duckdb")
    con.execute("CREATE TABLE marts.nova AS SELECT 1 AS x").complete()
    con.close()
    assert painel.ler(["nova"])["nova"].to_dict("list") == {"x": [1]}


# --- P4. Gráficos ---------------------------------------------------------------


def vendas():
    return pd.DataFrame(
        {
            "mes": pd.to_datetime(["2017-01-01", "2017-02-01", "2017-03-01"]),
            "pedidos": [10, 20, 30],
            "receita": [100.0, 200.0, 300.0],
        }
    )


def categorias(n):
    # Receita crescente: a maior é a última linha, para provar a ordenação.
    return pd.DataFrame(
        {"categoria": [f"cat{i:02d}" for i in range(n)], "receita": [float(i) for i in range(n)]}
    )


def pagamentos():
    return pd.DataFrame({"tipo_pagamento": ["boleto", "credit_card"], "pct_valor": [20.0, 80.0]})


def ticket():
    return pd.DataFrame({"uf": ["SP", "PB", "RJ"], "ticket_medio": [100.0, 200.0, 150.0]})


def clientes():
    return pd.DataFrame({"uf": ["RJ", "SP", "AC"], "clientes": [50, 100, 1]})


def notas(n):
    return pd.DataFrame(
        {
            "categoria": [f"cat{i:02d}" for i in range(n)],
            "nota_media": [5.0 - i / 10 for i in range(n)],
            # posicao_pior ao contrário da ordem das linhas
            "posicao_pior": list(range(n, 0, -1)),
        }
    )


def pareto():
    return pd.DataFrame({"posicao": [1, 2, 3, 4], "pct_receita_acumulada": [50.0, 80.0, 95.0, 100.0]})


def pontos(fig):
    return len(fig.data[0].x)


def eixo_y(fig):
    return list(fig.data[0].y)


def test_faturamento_tem_um_ponto_por_mes():
    fig = painel.faturamento_mensal(vendas())
    assert pontos(fig) == 3
    assert fig.layout.title.text == "01 · Faturamento mensal"
    assert fig.data[0].mode == "lines+markers"


def test_receita_por_categoria_tem_um_ponto_por_linha():
    assert pontos(painel.receita_por_categoria(categorias(4))) == 4


def test_receita_por_categoria_fica_no_top_10_com_a_maior_em_cima():
    fig = painel.receita_por_categoria(categorias(12))
    assert pontos(fig) == 10
    # Eixo invertido: a primeira categoria da lista é a de cima.
    assert eixo_y(fig)[0] == "cat11"
    assert fig.layout.yaxis.autorange == "reversed"


def test_mix_pagamento_tem_uma_barra_por_tipo():
    fig = painel.mix_pagamento(pagamentos())
    assert pontos(fig) == 2
    assert list(fig.data[0].x) == ["credit_card", "boleto"]


def test_ticket_por_uf_tem_a_maior_em_cima():
    fig = painel.ticket_medio_por_uf(ticket())
    assert pontos(fig) == 3
    assert eixo_y(fig) == ["PB", "RJ", "SP"]
    assert fig.layout.yaxis.autorange == "reversed"


def test_clientes_por_uf_tem_a_maior_em_cima():
    fig = painel.clientes_por_uf(clientes())
    assert pontos(fig) == 3
    assert eixo_y(fig) == ["SP", "RJ", "AC"]


def test_nota_por_categoria_tem_um_ponto_por_linha_e_a_pior_em_cima():
    fig = painel.nota_por_categoria(notas(4))
    assert pontos(fig) == 4
    assert eixo_y(fig) == ["cat03", "cat02", "cat01", "cat00"]
    assert fig.layout.yaxis.autorange == "reversed"


def test_nota_por_categoria_mostra_so_as_10_piores():
    assert pontos(painel.nota_por_categoria(notas(12))) == 10


def test_nota_por_categoria_desempata_pelo_nome():
    df = pd.DataFrame(
        {
            # b e a empatados no 1º lugar, nessa ordem de linha
            "categoria": ["b", "a", "c"],
            "nota_media": [3.0, 3.0, 4.0],
            "posicao_pior": [1, 1, 3],
        }
    )
    assert eixo_y(painel.nota_por_categoria(df)) == ["a", "b", "c"]


def test_concentracao_tem_um_ponto_por_vendedor_e_linha_tracejada_em_80():
    fig = painel.concentracao_vendedores(pareto())
    assert pontos(fig) == 4
    linha = fig.layout.shapes[0]
    assert (linha.y0, linha.y1, linha.line.dash) == (80, 80, "dash")


def test_cada_grafico_tem_uma_cor_so_e_titulo_com_o_numero_do_mart():
    figuras = {
        "01": painel.faturamento_mensal(vendas()),
        "02": painel.receita_por_categoria(categorias(3)),
        "09": painel.mix_pagamento(pagamentos()),
        "08": painel.ticket_medio_por_uf(ticket()),
        "07": painel.clientes_por_uf(clientes()),
        "04": painel.nota_por_categoria(notas(3)),
        "11": painel.concentracao_vendedores(pareto()),
    }
    for numero, fig in figuras.items():
        assert fig.layout.title.text.startswith(f"{numero} · ")
        assert len(fig.data) == 1, numero
        assert fig.data[0].marker.color == painel.COR, numero


def test_eixos_tem_unidade():
    assert painel.faturamento_mensal(vendas()).layout.yaxis.title.text == "Receita (R$)"
    assert painel.mix_pagamento(pagamentos()).layout.yaxis.title.text == "% do valor pago"
    assert painel.nota_por_categoria(notas(3)).layout.xaxis.title.text == "Nota média (1 a 5)"


def test_graficos_usam_separador_brasileiro():
    # Primeiro caractere: decimal; segundo: milhar.
    assert painel.mix_pagamento(pagamentos()).layout.separators == ",."
