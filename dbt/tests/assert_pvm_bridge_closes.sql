-- ADR-0001 Q1 criterion 1: the DB II bridge closes to the cent for every scope and month
select * from {{ ref('mart_db2_bridge') }} where abs(residual_db2) > 0.01
