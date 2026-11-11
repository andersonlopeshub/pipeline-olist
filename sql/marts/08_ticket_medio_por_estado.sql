-- Quanto cada estado gasta por pedido?
-- Grão: uma UF do cliente. Ignora pedidos cancelados e indisponíveis.
-- Receita = soma de price dos itens, sem frete (mesmo critério de 06_kpis).
WITH receita_pedido AS (
    SELECT
        c.customer_state     AS uf,
        p.order_id,
        sum(i.price)         AS receita,
        sum(i.freight_value) AS frete
    FROM refined.pedidos      AS p
    JOIN refined.clientes     AS c ON c.customer_id = p.customer_id
    JOIN refined.itens_pedido AS i ON i.order_id    = p.order_id
    WHERE p.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_state, p.order_id
)
SELECT
    uf,
    count(*)                                                   AS pedidos,
    sum(receita)                                               AS receita,
    round(avg(receita), 2)                                     AS ticket_medio,
    round(median(receita), 2)                                  AS ticket_mediana,
    round(avg(frete), 2)                                       AS frete_medio,
    round(100.0 * sum(frete) / (sum(receita) + sum(frete)), 1) AS pct_frete
FROM receita_pedido
GROUP BY uf
ORDER BY ticket_medio DESC;
