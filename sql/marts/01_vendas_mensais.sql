SELECT
    date_trunc('month', p.order_purchase_timestamp)::DATE AS mes,
    count(DISTINCT p.order_id)                            AS pedidos,
    sum(i.price)                                          AS receita
FROM refined.pedidos      AS p
JOIN refined.itens_pedido AS i ON i.order_id = p.order_id
WHERE p.order_status NOT IN ('canceled', 'unavailable')
GROUP BY mes
ORDER BY mes;