-- Como os clientes pagam?
-- Grão: um tipo de pagamento. Ignora pedidos cancelados e indisponíveis.
-- Um pedido pode usar mais de um tipo (ex.: cartão + voucher), então a
-- coluna pedidos não soma; valor e pct_valor somam.
SELECT
    pg.payment_type                                                              AS tipo_pagamento,
    count(DISTINCT pg.order_id)                                                  AS pedidos,
    count(*)                                                                     AS pagamentos,
    sum(pg.payment_value)                                                        AS valor,
    round(100.0 * sum(pg.payment_value) / sum(sum(pg.payment_value)) OVER (), 2) AS pct_valor,
    round(avg(pg.payment_value), 2)                                              AS valor_medio,
    round(avg(pg.payment_installments), 1)                                       AS parcelas_media,
    max(pg.payment_installments)                                                 AS parcelas_max
FROM refined.pagamentos AS pg
JOIN refined.pedidos    AS p ON p.order_id = pg.order_id
WHERE p.order_status NOT IN ('canceled', 'unavailable')
GROUP BY pg.payment_type
ORDER BY valor DESC;
