SELECT
    count(*)                                                                    AS entregues,
    count(*) FILTER (order_delivered_customer_date::DATE <= order_estimated_delivery_date) AS no_prazo,
    count(*) FILTER (order_delivered_customer_date::DATE >  order_estimated_delivery_date) AS atrasados,
    round(100.0 * no_prazo / entregues, 1)                                      AS pct_no_prazo
FROM refined.pedidos
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;
