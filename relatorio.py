"""Relatório estático do painel Olist: um relatorio.html na raiz.

Execução:
    uv run python relatorio.py

A spec do painel (docstring de painel.py) continua valendo aqui.

R1. MESMAS FUNÇÕES
    Lê os marts com painel.ler(), formata com painel.reais/pct/numero e
    monta os gráficos com as mesmas funções de painel.py. Não importa
    streamlit. Não desenha nenhum gráfico que não esteja em painel.py.
    Por quê: o relatório e o app.py não podem divergir no número nem no
    desenho.

R2. UM ARQUIVO SÓ
    Escreve relatorio.html na raiz, com as mesmas quatro faixas do app.py,
    na mesma ordem. Cartões em HTML simples, numa grade. Gráficos com
    figura.to_html(full_html=False); a biblioteca do plotly vem do CDN uma
    vez só, no primeiro gráfico (include_plotlyjs="cdn"), e nos outros
    include_plotlyjs=False. Cada gráfico com div_id fixo ("g01", "g02"...).
    Por quê: sem div_id o plotly sorteia um id novo a cada execução, e o
    arquivo muda sem o dado mudar.

R3. SEM FILTRO
    O faturamento mostra o mesmo período padrão do app.py (jan/2017 a
    ago/2018), e o título do gráfico diz o período.
    Por quê: o HTML não tem slider; quem lê precisa saber qual recorte vê.

R4. RODAPÉ
    Data e hora em que o arquivo foi gerado: "Dados de 25/10/2026 14:03".
    Por quê: o arquivo não fala com o banco; quem lê precisa saber de
    quando é o número.

R5. SAÍDA NA TELA
    Imprime o caminho do arquivo e o tamanho em KB. stdout em utf-8.

Critérios de aceite:
- Abrir relatorio.html com dois cliques mostra os sete cartões com os
  mesmos valores do app.py.
- O arquivo tem menos de 200 KB.
- Rodar duas vezes muda só a data do rodapé.
"""

import sys
from datetime import datetime
from html import escape
from pathlib import Path

import plotly.graph_objects as go

import painel

DESTINO = Path("relatorio.html")
COMANDO = "uv run python -m pipeline.marts"

ESTILO = """
body { margin: 0; padding: 24px 16px; background: #fcfcfb; color: #0b0b0b;
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 1.8rem; margin: 0 0 4px; }
.nota { color: #52514e; margin: 0 0 20px; font-size: .9rem; }
.cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
           gap: 12px; margin-bottom: 16px; }
.cartao { border: 1px solid #e3e2de; border-radius: 8px; padding: 12px 14px; background: #fff; }
.rotulo { color: #52514e; font-size: .85rem; line-height: 1.3; }
.valor { font-size: 1.6rem; font-weight: 600; margin-top: 6px; }
.tres { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
@media (max-width: 900px) { .tres { grid-template-columns: 1fr; } }
.grafico { background: #fff; border: 1px solid #e3e2de; border-radius: 8px;
           padding: 4px; margin-bottom: 16px; min-width: 0; }
footer { color: #52514e; font-size: .85rem; margin-top: 8px; }
"""


def carregar() -> dict:
    try:
        dados = painel.ler(painel.MARTS)
    except FileNotFoundError:
        print(f"Não encontrei o olist.duckdb na raiz do projeto. Rode: {COMANDO}", file=sys.stderr)
        sys.exit(1)
    faltando = [m for m in painel.MARTS if m not in dados]
    if faltando:
        lista = ", ".join(f"marts.{m}" for m in faltando)
        print(f"Faltam marts no olist.duckdb: {lista}. Rode: {COMANDO}", file=sys.stderr)
        sys.exit(1)
    return dados


def figuras(dados: dict) -> list[go.Figure]:
    """As sete figuras na ordem do app.py: faixa 2, depois 3 e 4."""
    vendas = dados["vendas_mensais"].sort_values("mes")
    inicio, fim = painel.PERIODO_PADRAO
    recorte = vendas[(vendas["mes"] >= inicio) & (vendas["mes"] <= fim)]
    faturamento = painel.faturamento_mensal(recorte)
    periodo = f"{painel.mes_curto(inicio)} a {painel.mes_curto(fim)}"
    faturamento.update_layout(title=f"{faturamento.layout.title.text} · {periodo}")

    lista = [
        faturamento,
        painel.receita_por_categoria(dados["top_categorias"]),
        painel.mix_pagamento(dados["mix_pagamento"]),
        painel.ticket_medio_por_uf(dados["ticket_medio_por_estado"]),
        painel.clientes_por_uf(dados["clientes_por_uf"]),
        painel.nota_por_categoria(dados["nota_por_categoria"]),
        painel.concentracao_vendedores(dados["vendedores_pareto"]),
    ]
    # No app.py o tema do Streamlit pinta o fundo; fora dele o padrão do
    # plotly é cinza-azulado. Só o fundo muda: o gráfico é o mesmo.
    for fig in lista:
        fig.update_layout(template="plotly_white")
    return lista


def divs(lista: list[go.Figure]) -> list[str]:
    return [
        '<div class="grafico">'
        + fig.to_html(
            full_html=False,
            include_plotlyjs="cdn" if i == 0 else False,
            div_id=f"g{i + 1:02d}",
        )
        + "</div>"
        for i, fig in enumerate(lista)
    ]


def pagina(dados: dict, gerado: datetime) -> str:
    cartoes = "\n".join(
        f'<div class="cartao"><div class="rotulo">{escape(rotulo)}</div>'
        f'<div class="valor">{escape(valor)}</div></div>'
        for rotulo, valor in painel.cartoes(dados)
    )
    g = divs(figuras(dados))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist · visão da operação</title>
<style>{ESTILO}</style>
</head>
<body>
<main>
<h1>Olist · visão da operação</h1>
<p class="nota">os cartões valem para o período inteiro</p>
<section class="cartoes">
{cartoes}
</section>
<section>
{g[0]}
</section>
<section class="tres">
{g[1]}
{g[2]}
{g[3]}
</section>
<section class="tres">
{g[4]}
{g[5]}
{g[6]}
</section>
<footer>Dados de {gerado.strftime("%d/%m/%Y %H:%M")}</footer>
</main>
</body>
</html>
"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    dados = carregar()
    # newline="\n": o Windows gravaria \r\n, e o arquivo mudaria de acordo
    # com a máquina que rodou.
    DESTINO.write_text(pagina(dados, datetime.now()), encoding="utf-8", newline="\n")
    kb = DESTINO.stat().st_size / 1024
    print(f"{DESTINO.resolve()}  {painel.numero(kb, 1)} KB")


if __name__ == "__main__":
    main()
