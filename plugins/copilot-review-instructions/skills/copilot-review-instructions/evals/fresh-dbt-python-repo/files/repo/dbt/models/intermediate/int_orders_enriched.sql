with orders as (
    select * from {{ ref('stg_erp__orders') }}
),

accounts as (
    -- TODO: move to stg model; reviewers keep flagging this
    select id as account_id, industry from {{ source('salesforce', 'account') }}
),

joined as (
    select
        orders.order_id,
        orders.customer_id,
        orders.account_id,
        orders.net_amount_eur,
        orders.order_date,
        orders.order_status,
        accounts.industry
    from orders
    left join accounts on orders.account_id = accounts.account_id
)

select * from joined
