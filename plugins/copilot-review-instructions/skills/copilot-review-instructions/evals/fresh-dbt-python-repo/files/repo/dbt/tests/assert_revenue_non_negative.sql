select order_id from {{ ref('fct_revenue') }} where revenue_eur < 0
