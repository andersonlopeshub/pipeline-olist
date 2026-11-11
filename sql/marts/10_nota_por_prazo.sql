-- Atrasar a entrega derruba a nota?
-- Grão: uma faixa de prazo (entrega real vs. data prometida).
-- Só pedidos entregues e avaliados. Nota por pedido = média das avaliações
-- dele (mesmo critério de 04_nota_por_categoria).
WITH nota_pedido AS (
    SELECT order_id, avg(review_score) AS nota
    FROM refined.avaliacoes
    GROUP BY order_id
),
prazo_pedido AS (
    SELECT
        order_id,
        date_diff('day', order_estimated_delivery_date,
                         order_delivered_customer_date::DATE) AS dias_atraso
    FROM refined.pedidos
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
),
faixa_pedido AS (
    SELECT
        n.nota,
        CASE
            WHEN pr.dias_atraso <= -7 THEN 1
            WHEN pr.dias_atraso <   0 THEN 2
            WHEN pr.dias_atraso =   0 THEN 3
            WHEN pr.dias_atraso <=  3 THEN 4
            WHEN pr.dias_atraso <=  7 THEN 5
            ELSE 6
        END AS ordem
    FROM prazo_pedido AS pr
    JOIN nota_pedido  AS n ON n.order_id = pr.order_id
)
SELECT
    ordem,
    CASE ordem
        WHEN 1 THEN '7+ dias antes'
        WHEN 2 THEN '1 a 6 dias antes'
        WHEN 3 THEN 'no dia'
        WHEN 4 THEN '1 a 3 dias de atraso'
        WHEN 5 THEN '4 a 7 dias de atraso'
        WHEN 6 THEN '8+ dias de atraso'
    END                                                      AS faixa_prazo,
    count(*)                                                 AS pedidos,
    round(100.0 * count(*) / sum(count(*)) OVER (), 2)       AS pct_pedidos,
    round(avg(nota), 2)                                      AS nota_media,
    round(100.0 * count(*) FILTER (nota <= 2) / count(*), 1) AS pct_nota_baixa
FROM faixa_pedido
GROUP BY ordem
ORDER BY ordem;
