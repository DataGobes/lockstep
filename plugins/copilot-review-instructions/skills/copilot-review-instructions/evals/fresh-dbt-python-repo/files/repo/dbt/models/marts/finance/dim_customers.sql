with customers as (
    select * from {{ ref('stg_erp__customers') }}
),

accounts as (
    select * from {{ ref('stg_salesforce__accounts') }}
)

select
    customers.customer_id,
    customers.customer_name,
    customers.country_code,
    accounts.industry
from customers
left join accounts on customers.account_id = accounts.account_id
