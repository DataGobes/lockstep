with source as (
    select * from {{ source('erp', 'orders') }}
),

renamed as (
    select
        order_no as order_id,
        cust_no as customer_id,
        sf_account_id as account_id,
        {{ cents_to_euros('net_amount_cents') }} as net_amount_eur,
        cast(order_date as date) as order_date,
        status as order_status,
        _loaded_at
    from source
)

select * from renamed
