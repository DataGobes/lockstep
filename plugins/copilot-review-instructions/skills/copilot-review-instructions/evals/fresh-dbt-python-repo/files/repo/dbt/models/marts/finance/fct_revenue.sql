with orders as (
    select * from {{ ref('int_orders_enriched') }}
)

select
    order_id,
    customer_id,
    order_date,
    industry,
    net_amount_eur as revenue_eur
from orders
where order_status = 'COMPLETED'
