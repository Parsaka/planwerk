-- Betriebsergebnis CO reconciles to the GuV operating result without residual
select * from {{ ref('mart_reconciliation_co_gkv') }} where abs(residual_eur) > 0.01
