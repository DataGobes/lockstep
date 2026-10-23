with source as (
    select * from {{ source('salesforce', 'opportunity') }}
),

renamed as (
    select
        id as opportunity_id,
        accountid as account_id,
        stagename as stage_name,
        {{ cents_to_euros('amount_cents') }} as amount_eur,
        cast(closedate as date) as close_date,
        iswon as is_won,
        _loaded_at
    from source
    where not isdeleted
)

select * from renamed
