-- Quanto demora para chegar em cada estado, e quanto atrasa?
-- Grão: uma UF do cliente. Só pedidos entregues com data de entrega.
-- Atraso = entrega real depois da data prometida (mesmo critério de
-- 03_entrega_no_prazo).
WITH entrega_pedido AS (
    SELECT
        c.customer_state AS uf,
        date_diff('day', p.order_purchase_timestamp,
                         p.order_delivered_customer_date)       AS dias_entrega,
        date_diff('day', p.order_estimated_delivery_date,
                         p.order_delivered_customer_date::DATE) AS dias_atraso
    FROM refined.pedidos  AS p
    JOIN refined.clientes AS c ON c.customer_id = p.customer_id
    WHERE p.order_status = 'delivered'
      AND p.order_delivered_customer_date IS NOT NULL
)
SELECT
    uf,
    count(*)                                                       AS entregues,
    round(avg(dias_entrega), 1)                                    AS dias_entrega_media,
    median(dias_entrega)                                           AS dias_entrega_mediana,
    quantile_cont(dias_entrega, 0.9)                               AS dias_entrega_p90,
    count(*) FILTER (dias_atraso > 0)                              AS atrasados,
    round(100.0 * count(*) FILTER (dias_atraso > 0) / count(*), 1) AS pct_atraso,
    round(avg(dias_atraso) FILTER (dias_atraso > 0), 1)            AS dias_atraso_medio
FROM entrega_pedido
GROUP BY uf
ORDER BY dias_entrega_media DESC;
