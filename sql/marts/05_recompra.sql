WITH pedidos_por_pessoa AS (
SELECT
        c.customer_unique_id,
        count(*) AS pedidos
    FROM refined.pedidos  AS p
    JOIN refined.clientes AS c ON c.customer_id = p.customer_id
    WHERE p.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_unique_id
)
SELECT
    pedidos                                            AS pedidos_por_cliente,
    count(*)                                           AS clientes,
    round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct_clientes
FROM pedidos_por_pessoa
GROUP BY pedidos
ORDER BY pedidos_por_cliente;
