"""Testes de relatorio.py (R1 a R5).

relatorio.py lê "olist.duckdb" e grava "relatorio.html" relativos à pasta
corrente: o teste faz chdir para tmp_path e cria lá os dez marts com dados
inventados.
"""

from datetime import datetime

import duckdb
import pytest

import painel
import relatorio

MARTS = {
    "kpis": "SELECT 150.5 AS ticket_medio, 1.25 AS pct_cancelados, 12.0 AS pct_frete, "
    "9.5 AS dias_entrega, 4.2 AS nota_media",
    # 90% compraram uma vez: recompra 10,00%
    "recompra": "SELECT * FROM (VALUES (1, 90.0), (2, 10.0)) t(pedidos_por_cliente, pct_clientes)",
    "entrega_no_prazo": "SELECT 88.8 AS pct_no_prazo",
    "vendas_mensais": """SELECT * FROM (VALUES
        (DATE '2016-12-01', 1.0),   -- antes do período padrão: fora
        (DATE '2017-01-01', 10.0),  -- primeiro mês do período
        (DATE '2018-08-01', 20.0),  -- último mês do período
        (DATE '2018-09-01', 2.0)    -- depois do período: fora
        ) t(mes, receita)""",
    "top_categorias": "SELECT * FROM (VALUES ('a', 10.0), ('b', 5.0)) t(categoria, receita)",
    "mix_pagamento": "SELECT * FROM (VALUES ('boleto', 100.0)) t(tipo_pagamento, pct_valor)",
    "ticket_medio_por_estado": "SELECT * FROM (VALUES ('PB', 200.0), ('SP', 100.0)) t(uf, ticket_medio)",
    "clientes_por_uf": "SELECT * FROM (VALUES ('SP', 10), ('AC', 1)) t(uf, clientes)",
    "nota_por_categoria": "SELECT * FROM (VALUES ('a', 3.0, 1)) t(categoria, nota_media, posicao_pior)",
    "vendedores_pareto": "SELECT * FROM (VALUES (1, 80.0), (2, 100.0)) t(posicao, pct_receita_acumulada)",
}


def criar_banco(pasta, sem=None):
    con = duckdb.connect(pasta / "olist.duckdb")
    con.execute("CREATE SCHEMA marts").complete()
    for nome, sql in MARTS.items():
        if nome != sem:
            con.execute(f"CREATE TABLE marts.{nome} AS {sql}").complete()
    con.close()


class Relogio:
    """Substitui relatorio.datetime: cada now() devolve a próxima hora da lista."""

    horas = []

    @classmethod
    def now(cls):
        return cls.horas.pop(0)


def preparar(tmp_path, monkeypatch, *horas, sem=None):
    monkeypatch.chdir(tmp_path)
    criar_banco(tmp_path, sem)
    monkeypatch.setattr(Relogio, "horas", list(horas))
    monkeypatch.setattr(relatorio, "datetime", Relogio)


def gerar(tmp_path):
    relatorio.main()
    return (tmp_path / "relatorio.html").read_text(encoding="utf-8")


def test_gera_o_arquivo_na_pasta_corrente(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 10, 25, 14, 3))
    relatorio.main()
    assert (tmp_path / "relatorio.html").is_file()


def test_rodar_duas_vezes_muda_so_o_rodape(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 10, 25, 14, 3), datetime(2026, 10, 26, 9, 0))
    primeira = gerar(tmp_path).splitlines()
    segunda = gerar(tmp_path).splitlines()
    diferentes = [(a, b) for a, b in zip(primeira, segunda) if a != b]
    assert len(primeira) == len(segunda)
    assert diferentes == [
        ("<footer>Dados de 25/10/2026 14:03</footer>", "<footer>Dados de 26/10/2026 09:00</footer>")
    ]


def test_cartoes_do_html_tem_os_valores_do_painel(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 10, 25, 14, 3))
    html = gerar(tmp_path)
    dados = painel.ler(painel.MARTS)
    for rotulo, valor in painel.cartoes(dados):
        assert f'<div class="rotulo">{rotulo}</div><div class="valor">{valor}</div>' in html
    assert '<div class="valor">10,00%</div>' in html  # recompra: 100 - 90


def test_plotly_vem_do_cdn_uma_vez_so(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 10, 25, 14, 3))
    assert gerar(tmp_path).count("cdn.plot.ly") == 1


def test_cada_grafico_tem_div_id_fixo_na_ordem(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 10, 25, 14, 3))
    html = gerar(tmp_path)
    posicoes = [html.index(f'id="g{i:02d}"') for i in range(1, 8)]
    assert posicoes == sorted(posicoes)
    assert 'id="g08"' not in html


def test_faturamento_mostra_so_o_periodo_padrao_e_diz_qual_no_titulo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    figuras = relatorio.figuras(painel.ler(painel.MARTS))
    faturamento = figuras[0]
    # Das quatro linhas inventadas, só jan/2017 e ago/2018 estão no período.
    assert len(faturamento.data[0].x) == 2
    assert faturamento.layout.title.text == "01 · Faturamento mensal · jan/2017 a ago/2018"


def test_relatorio_usa_os_sete_graficos_do_painel_na_ordem_do_app(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    titulos = [f.layout.title.text[:2] for f in relatorio.figuras(painel.ler(painel.MARTS))]
    assert titulos == ["01", "02", "09", "08", "07", "04", "11"]


def test_rodape_tem_a_data_e_a_hora_da_geracao(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, datetime(2026, 1, 5, 8, 7))
    assert "<footer>Dados de 05/01/2026 08:07</footer>" in gerar(tmp_path)


def test_sem_banco_encerra_sem_gerar_arquivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        relatorio.main()
    assert list(tmp_path.iterdir()) == []


def test_mart_faltando_encerra_sem_gerar_arquivo(tmp_path, monkeypatch):
    # mix_pagamento tem o mesmo nome de uma função de painel.py: o caso que
    # o replacement scan do DuckDB quebrava antes de chegar ao sys.exit.
    preparar(tmp_path, monkeypatch, sem="mix_pagamento")
    with pytest.raises(SystemExit):
        relatorio.main()
    assert not (tmp_path / "relatorio.html").exists()
