with source as (
    select * from {{ source('erp', 'customers') }}
),

renamed as (
    select
        cust_no as customer_id,
        sf_account_id as account_id,
        cust_name as customer_name,
        country_code,
        _loaded_at
    from source
)

select * from renamed
