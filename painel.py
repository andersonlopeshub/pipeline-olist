"""Painel Olist: leitura dos marts, formatação de números e gráficos.

Este módulo não importa streamlit. A página é app.py:
    uv run streamlit run app.py

P1. LEITURA
    ler(marts) -> dict nome -> DataFrame. Para cada nome, só
    SELECT * FROM marts.<nome>. Nenhuma outra SQL.
    Conexão com duckdb.connect("olist.duckdb", read_only=True), aberta e
    fechada dentro de ler().
    Por quê: conexão aberta segura o arquivo, e o pipeline.marts não
    consegue gravar com o painel de pé.

P2. NENHUM CÁLCULO
    Proibido aqui e em app.py: agrupar, somar, tirar média, contar, juntar
    tabelas, girar linhas em colunas, e qualquer conta entre colunas. Permitido: ordenar,
    filtrar linhas, head(n), renomear coluna e formatar texto.
    Única exceção, em cartoes() deste arquivo: o cartão Recompra é
    100 - pct_clientes da linha pedidos_por_cliente = 1 do mart 05, porque
    o mart guarda o complemento. Fica aqui, e não em app.py, para o
    relatorio.py mostrar o mesmo número sem repetir a conta.
    Por quê: número novo na tela exige um .sql novo em marts. Se faltar
    algum número, o certo é criar o mart, não fazer a conta no painel.

P3. LAYOUT (app.py), de cima para baixo, layout="wide"
    Cabeçalho: título "Olist · visão da operação" à esquerda; à direita,
      o filtro de período (P5).
    Faixa 1: sete cartões (st.metric), nesta ordem, cada rótulo com a
      definição curta: Ticket médio (kpis.ticket_medio, reais) ·
      Cancelados (kpis.pct_cancelados, 2 casas) · Peso do frete
      (kpis.pct_frete, 1 casa) · Recompra (2 casas) · No prazo
      (entrega_no_prazo.pct_no_prazo, 1 casa) · Dias até entregar
      (kpis.dias_entrega, 1 casa) · Nota média (kpis.nota_media, 2 casas).
    Faixa 2, largura inteira: faturamento mensal, linha com marcadores.
    Faixa 3, três colunas iguais: receita por categoria (top 10, barras
      horizontais, maior em cima); mix de pagamento (barras por
      pct_valor); ticket médio por UF (barras horizontais, maior em cima).
    Faixa 4, três colunas iguais: clientes por UF (barras horizontais,
      maior em cima); nota por categoria (as 10 primeiras por
      posicao_pior, pontos, pior em cima); concentração de vendedores
      (linha de pct_receita_acumulada por posicao, com linha horizontal
      tracejada em 80).
    Cada gráfico: título com o número do mart ("01 · Faturamento mensal"),
    uma cor só, eixo com unidade, width="stretch".
    Por quê: o título com o número leva direto ao .sql que gerou o
    gráfico; uma cor só porque nenhum gráfico compara séries.

P4. FORMATO
    reais(valor, casas=2)  -> "R$ 1.003.862,14"
    pct(valor, casas=1)    -> "93,2%"
    numero(valor, casas=0) -> "96.470"
    Funções puras, sem streamlit e sem banco. Milhar com ponto, decimal
    com vírgula, sempre. Não usa o locale do sistema.
    Por quê: o resultado não pode depender da máquina de quem roda.
    Uma função por gráfico, recebendo o DataFrame do mart e devolvendo a
    figura plotly.
    Por quê: o relatório HTML reaproveita as mesmas funções.

P5. FILTRO DE PERÍODO (app.py)
    st.select_slider com os meses de vendas_mensais, padrão de jan/2017 a
    ago/2018. Recorta só as linhas do gráfico de faturamento. Os cartões e
    os outros gráficos não mudam, e a página diz isso embaixo do filtro:
    "os cartões valem para o período inteiro".
    Por quê: recortar linha é SELECT; recalcular cartão por período seria
    regra de negócio fora do SQL.

P6. CACHE E ERRO (app.py)
    Leitura com st.cache_data. Um botão "Recarregar dados" limpa o cache.
    Sem olist.duckdb, ou faltando qualquer mart usado em P3: st.error
    dizendo quais e o comando "uv run python -m pipeline.marts", e
    st.stop().
    Por quê: o painel não pode mostrar tela vazia ou parcial sem dizer o
    que fazer; o cache evita reler o banco a cada clique.

Critérios de aceite:
- Os sete cartões mostram: R$ 137,42 · 0,63% · 14,2% · 3,04% · 93,2% ·
  12,5 · 4,09.
- O faturamento abre com 20 meses (jan/2017 a ago/2018) e, com o filtro
  aberto até as pontas, mostra os 24.
- Top 10 de categorias com health_beauty em cima; nota com
  office_furniture em cima; ticket por UF com PB em cima e SP embaixo.
- Uma busca pelos nomes das operações proibidas em P2 em painel.py e
  app.py não encontra nada.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de
  lock.
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

BANCO = "olist.duckdb"

# Os marts que a tela usa (P3). nota_por_prazo e tempo_entrega_por_estado
# existem no banco, mas não entram nesta tela.
MARTS = [
    "kpis",
    "recompra",
    "entrega_no_prazo",
    "vendas_mensais",
    "top_categorias",
    "mix_pagamento",
    "ticket_medio_por_estado",
    "clientes_por_uf",
    "nota_por_categoria",
    "vendedores_pareto",
]

# Período padrão do faturamento (P5).
PERIODO_PADRAO = (pd.Timestamp("2017-01-01"), pd.Timestamp("2018-08-01"))

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Azul da paleta de referência: passa contraste nos fundos claro e escuro.
COR = "#2a78d6"
COR_REFERENCIA = "#8a8984"


# --- P1. Leitura ------------------------------------------------------------


def ler(marts: list[str]) -> dict[str, pd.DataFrame]:
    """Lê cada mart com SELECT *. Mart que não existe fica fora do dict.

    Levanta FileNotFoundError se olist.duckdb não existir: com read_only o
    DuckDB não cria o arquivo, mas o erro dele não diz que é falta do banco.
    """
    if not Path(BANCO).exists():
        raise FileNotFoundError(BANCO)
    dados: dict[str, pd.DataFrame] = {}
    con = duckdb.connect(BANCO, read_only=True)
    try:
        for nome in marts:
            try:
                dados[nome] = con.execute(f'SELECT * FROM marts."{nome}"').df()
            except duckdb.CatalogException:
                # Quem chama compara o dict com a lista pedida; assim não é
                # preciso outra SQL para descobrir o que existe.
                continue
    finally:
        con.close()
    return dados


# --- P4. Formato ------------------------------------------------------------


def _br(valor: float, casas: int) -> str:
    # Formata no padrão americano e troca os separadores: não depende do
    # locale da máquina.
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def reais(valor: float, casas: int = 2) -> str:
    return f"R$ {_br(valor, casas)}"


def pct(valor: float, casas: int = 1) -> str:
    return f"{_br(valor, casas)}%"


def numero(valor: float, casas: int = 0) -> str:
    return _br(valor, casas)


def mes_curto(mes: pd.Timestamp) -> str:
    # Nome do mês pela lista MESES, não por strftime: %b depende do locale.
    return f"{MESES[mes.month - 1]}/{mes.year}"


# --- P3. Cartões ------------------------------------------------------------


def cartoes(dados: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
    """Os sete cartões da faixa 1, na ordem: (rótulo, valor formatado)."""
    kpis = dados["kpis"].iloc[0]
    recompra = dados["recompra"]
    um_pedido = recompra.loc[recompra["pedidos_por_cliente"] == 1, "pct_clientes"].iloc[0]
    no_prazo = dados["entrega_no_prazo"]["pct_no_prazo"].iloc[0]
    return [
        ("Ticket médio · receita por pedido, sem frete", reais(kpis["ticket_medio"])),
        ("Cancelados · % de todos os pedidos", pct(kpis["pct_cancelados"], 2)),
        ("Peso do frete · % do frete no total pago", pct(kpis["pct_frete"], 1)),
        # Única conta permitida (P2): o mart 05 guarda quem comprou uma vez só.
        ("Recompra · % de clientes com 2+ pedidos", pct(100 - um_pedido, 2)),
        ("No prazo · % entregues até a data prometida", pct(no_prazo, 1)),
        ("Dias até entregar · média da compra à entrega", numero(kpis["dias_entrega"], 1)),
        ("Nota média · avaliações de 1 a 5", numero(kpis["nota_media"], 2)),
    ]


# --- P4. Gráficos -----------------------------------------------------------


def _estilo(fig: go.Figure, titulo: str, x: str, y: str, altura: int) -> go.Figure:
    fig.update_traces(marker_color=COR)
    fig.update_layout(
        title=titulo,
        xaxis_title=x,
        yaxis_title=y,
        height=altura,
        # Separadores do plotly (decimal, milhar): eixos e tooltips no
        # padrão brasileiro, sem locale.
        separators=",.",
        showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
        barcornerradius=4,
    )
    return fig


def _barras_deitadas(fig: go.Figure) -> go.Figure:
    # O plotly desenha a primeira linha do DataFrame embaixo; invertendo o
    # eixo, a ordem da tabela vira a ordem de cima para baixo.
    fig.update_yaxes(autorange="reversed")
    return fig


def faturamento_mensal(df: pd.DataFrame) -> go.Figure:
    fig = px.line(df, x="mes", y="receita", markers=True)
    fig.update_traces(
        line=dict(color=COR, width=2),
        marker=dict(size=8),
        hovertemplate="%{x|%m/%Y}<br>R$ %{y:,.2f}<extra></extra>",
    )
    fig.update_xaxes(tickformat="%m/%Y")
    return _estilo(fig, "01 · Faturamento mensal", "Mês", "Receita (R$)", 380)


def receita_por_categoria(df: pd.DataFrame) -> go.Figure:
    top = df.sort_values("receita", ascending=False).head(10)
    fig = px.bar(top, x="receita", y="categoria", orientation="h")
    fig.update_traces(hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>")
    fig = _barras_deitadas(fig)
    return _estilo(fig, "02 · Receita por categoria", "Receita (R$)", "", 420)


def mix_pagamento(df: pd.DataFrame) -> go.Figure:
    ordem = df.sort_values("pct_valor", ascending=False)
    fig = px.bar(ordem, x="tipo_pagamento", y="pct_valor")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.2f}%<extra></extra>")
    return _estilo(fig, "09 · Mix de pagamento", "", "% do valor pago", 420)


def ticket_medio_por_uf(df: pd.DataFrame) -> go.Figure:
    ordem = df.sort_values("ticket_medio", ascending=False)
    fig = px.bar(ordem, x="ticket_medio", y="uf", orientation="h")
    fig.update_traces(hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>")
    fig = _barras_deitadas(fig)
    return _estilo(fig, "08 · Ticket médio por UF", "Ticket médio (R$)", "", 620)


def clientes_por_uf(df: pd.DataFrame) -> go.Figure:
    ordem = df.sort_values("clientes", ascending=False)
    fig = px.bar(ordem, x="clientes", y="uf", orientation="h")
    fig.update_traces(hovertemplate="%{y}<br>%{x:,} clientes<extra></extra>")
    fig = _barras_deitadas(fig)
    return _estilo(fig, "07 · Clientes por UF", "Clientes (pessoas)", "", 620)


def nota_por_categoria(df: pd.DataFrame) -> go.Figure:
    # rank() empata (bed_bath_table e home_construction dividem o 9º lugar):
    # sem o segundo critério a ordem dos empatados muda entre execuções.
    piores = df.sort_values(["posicao_pior", "categoria"]).head(10)
    fig = px.scatter(piores, x="nota_media", y="categoria")
    fig.update_traces(
        marker=dict(size=10),
        hovertemplate="%{y}<br>nota %{x:,.2f}<extra></extra>",
    )
    fig = _barras_deitadas(fig)
    return _estilo(fig, "04 · Nota por categoria", "Nota média (1 a 5)", "", 620)


def concentracao_vendedores(df: pd.DataFrame) -> go.Figure:
    ordem = df.sort_values("posicao")
    fig = px.line(ordem, x="posicao", y="pct_receita_acumulada")
    fig.update_traces(
        line=dict(color=COR, width=2),
        hovertemplate="%{x:,}º vendedor<br>%{y:,.2f}% da receita<extra></extra>",
    )
    fig.add_hline(y=80, line_dash="dash", line_color=COR_REFERENCIA, line_width=1)
    return _estilo(
        fig,
        "11 · Concentração de vendedores",
        "Vendedores (posição por receita)",
        "% acumulado da receita",
        620,
    )
