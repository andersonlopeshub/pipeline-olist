"""Página do painel Olist. A spec está em painel.py.

Execução:
    uv run streamlit run app.py
"""

import pandas as pd
import streamlit as st

import painel

COMANDO = "uv run python -m pipeline.marts"


class MartsFaltando(Exception):
    pass


@st.cache_data
def carregar() -> dict[str, pd.DataFrame]:
    dados = painel.ler(painel.MARTS)
    faltando = [m for m in painel.MARTS if m not in dados]
    # Levantar em vez de devolver: o cache_data não guarda exceção, então
    # depois de rodar o pipeline a próxima atualização da página já relê.
    if faltando:
        raise MartsFaltando(faltando)
    return dados


st.set_page_config(page_title="Olist · visão da operação", layout="wide")

try:
    dados = carregar()
except FileNotFoundError:
    st.error(f"Não encontrei o olist.duckdb na raiz do projeto. Rode: `{COMANDO}`")
    st.stop()
except MartsFaltando as e:
    lista = ", ".join(f"marts.{m}" for m in e.args[0])
    st.error(f"Faltam marts no olist.duckdb: {lista}. Rode: `{COMANDO}`")
    st.stop()

vendas = dados["vendas_mensais"].sort_values("mes")

# --- Cabeçalho --------------------------------------------------------------

esquerda, direita = st.columns([3, 2])
esquerda.title("Olist · visão da operação")
with direita:
    inicio, fim = st.select_slider(
        "Período do faturamento",
        options=list(vendas["mes"]),
        value=painel.PERIODO_PADRAO,
        format_func=painel.mes_curto,
    )
    st.caption("os cartões valem para o período inteiro")
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

# --- Faixa 1: cartões -------------------------------------------------------

cartoes = painel.cartoes(dados)
for coluna, (rotulo, valor) in zip(st.columns(len(cartoes)), cartoes):
    coluna.metric(rotulo, valor, border=True)

# --- Faixa 2: faturamento ---------------------------------------------------

recorte = vendas[(vendas["mes"] >= inicio) & (vendas["mes"] <= fim)]
st.plotly_chart(painel.faturamento_mensal(recorte), width="stretch")

# --- Faixas 3 e 4 -----------------------------------------------------------

c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.receita_por_categoria(dados["top_categorias"]), width="stretch")
c2.plotly_chart(painel.mix_pagamento(dados["mix_pagamento"]), width="stretch")
c3.plotly_chart(painel.ticket_medio_por_uf(dados["ticket_medio_por_estado"]), width="stretch")

c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.clientes_por_uf(dados["clientes_por_uf"]), width="stretch")
c2.plotly_chart(painel.nota_por_categoria(dados["nota_por_categoria"]), width="stretch")
c3.plotly_chart(painel.concentracao_vendedores(dados["vendedores_pareto"]), width="stretch")
