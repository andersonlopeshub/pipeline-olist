-- KPIs gerais do negócio numa linha só.
-- Grão: uma linha. Receita e ticket ignoram pedidos cancelados e indisponíveis.
WITH receita_pedido AS (
    SELECT
        p.order_id,
        sum(i.price)         AS receita,
        sum(i.freight_value) AS frete
    FROM refined.pedidos      AS p
    JOIN refined.itens_pedido AS i ON i.order_id = p.order_id
    WHERE p.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY p.order_id
),
venda AS (
    SELECT
        round(avg(receita), 2)                                     AS ticket_medio,
        round(median(receita), 2)                                  AS ticket_mediana,
        round(100.0 * sum(frete) / (sum(receita) + sum(frete)), 1) AS pct_frete
    FROM receita_pedido
),
cancelamento AS (
    SELECT round(100.0 * count(*) FILTER (order_status = 'canceled') / count(*), 2) AS pct_cancelados
    FROM refined.pedidos
),
entrega AS (
    SELECT
        round(avg(date_diff('day', order_purchase_timestamp, order_delivered_customer_date)), 1) AS dias_entrega,
        median(date_diff('day', order_purchase_timestamp, order_delivered_customer_date))        AS dias_entrega_mediana
    FROM refined.pedidos
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
),
satisfacao AS (
    SELECT round(avg(review_score), 2) AS nota_media
    FROM refined.avaliacoes
)
SELECT *
FROM venda, cancelamento, entrega, satisfacao;
