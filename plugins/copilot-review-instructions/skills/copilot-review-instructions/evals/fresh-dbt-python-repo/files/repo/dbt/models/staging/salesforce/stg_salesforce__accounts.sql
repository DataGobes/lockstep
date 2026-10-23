with source as (
    select * from {{ source('salesforce', 'account') }}
),

renamed as (
    select
        id as account_id,
        name as account_name,
        industry,
        billingcountry as billing_country,
        cast(createddate as timestamp) as created_at,
        _loaded_at
    from source
    where not isdeleted
)

select * from renamed
