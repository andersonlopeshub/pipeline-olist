-- Poucos vendedores concentram a receita? (curva ABC / Pareto)
-- Grão: um vendedor. Ignora pedidos cancelados e indisponíveis.
-- Classe A = vendedores que formam os primeiros 80% da receita, B = de 80%
-- a 95%, C = o resto. Empate de receita é desfeito por seller_id para a
-- ordem não mudar entre execuções.
WITH por_vendedor AS (
    SELECT
        i.seller_id,
        count(DISTINCT i.order_id) AS pedidos,
        count(*)                   AS itens,
        sum(i.price)               AS receita
    FROM refined.itens_pedido AS i
    JOIN refined.pedidos      AS p ON p.order_id = i.order_id
    WHERE p.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY i.seller_id
),
acumulado AS (
    SELECT
        row_number() OVER w                                AS posicao,
        seller_id,
        pedidos,
        itens,
        receita,
        100.0 * receita / sum(receita) OVER ()             AS pct_receita,
        100.0 * sum(receita) OVER w / sum(receita) OVER () AS pct_receita_acumulada,
        100.0 * row_number() OVER w / count(*) OVER ()     AS pct_vendedores_acumulado
    FROM por_vendedor
    WINDOW w AS (ORDER BY receita DESC, seller_id
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT
    a.posicao,
    a.seller_id,
    v.seller_state                       AS uf,
    a.pedidos,
    a.itens,
    a.receita,
    round(a.pct_receita, 3)              AS pct_receita,
    round(a.pct_receita_acumulada, 2)    AS pct_receita_acumulada,
    round(a.pct_vendedores_acumulado, 2) AS pct_vendedores_acumulado,
    -- Classe pelo acumulado ANTES do vendedor: quem cruza a linha dos 80%
    -- ainda entra em A.
    CASE
        WHEN a.pct_receita_acumulada - a.pct_receita < 80 THEN 'A'
        WHEN a.pct_receita_acumulada - a.pct_receita < 95 THEN 'B'
        ELSE 'C'
    END                                  AS classe
FROM acumulado               AS a
LEFT JOIN refined.vendedores AS v ON v.seller_id = a.seller_id
ORDER BY a.posicao;
