-- Betriebsabrechnungsbogen: step-down allocation (Stufenleiterverfahren) of the service cost
-- centres per company code, version and period. Senders and keys come from seed bab_cycle.
-- A sender allocates its primary costs plus everything it received in earlier steps to all
-- cost centres that are valid in the period, have a positive key and are not a sender of
-- this or an earlier step.
{% set max_steps = 3 %}
with primary_cost as (
    select version, company_code, period, cost_centre,
           sum(amount_lc) as amount_lc, sum(amount_eur) as amount_eur, sum(amount_cc_eur) as amount_cc_eur
    from {{ ref('int_cost_centre_primary') }}
    group by all
),
keys as (
    select k.*, c.valid_from, c.valid_to
    from {{ ref('stg_s4__allocation_keys') }} k
    join (select cost_centre, min(valid_from) valid_from, max(valid_to) valid_to
          from {{ ref('stg_s4__cost_centres') }} group by cost_centre) c on c.cost_centre = k.cost_centre
),
cycle as (select cast(company_code as varchar) company_code, step, cast(sender as varchar) sender, allocation_key
          from {{ ref('bab_cycle') }}),
periods as (select distinct version, company_code, period from primary_cost),
{% for s in range(1, max_steps + 1) %}
receivers_{{ s }} as (
    select p.version, p.company_code, p.period, cy.sender, k.cost_centre as receiver,
           case cy.allocation_key when 'key_it' then k.key_it
                                  when 'key_energy' then k.key_energy
                                  else k.key_maintenance end as key_value
    from periods p
    join cycle cy on cy.company_code = p.company_code and cy.step = {{ s }}
    join keys k on k.company_code = p.company_code
     and cast(p.period || '-01' as date) between k.valid_from and k.valid_to
    left join cycle done on done.company_code = p.company_code and done.step <= {{ s }} and done.sender = k.cost_centre
    where done.sender is null
),
{% if s > 1 %}
received_{{ s }} as (
    select version, company_code, period, receiver,
           sum(amount_lc) as amount_lc, sum(amount_eur) as amount_eur, sum(amount_cc_eur) as amount_cc_eur
    from ({% for t in range(1, s) %}select * from alloc_{{ t }}{% if not loop.last %} union all {% endif %}{% endfor %}) x
    group by all
),
{% endif %}
sender_total_{{ s }} as (
    select p.version, p.company_code, p.period, cy.sender,
           coalesce(pc.amount_lc, 0){% if s > 1 %} + coalesce(rc.amount_lc, 0){% endif %} as amount_lc,
           coalesce(pc.amount_eur, 0){% if s > 1 %} + coalesce(rc.amount_eur, 0){% endif %} as amount_eur,
           coalesce(pc.amount_cc_eur, 0){% if s > 1 %} + coalesce(rc.amount_cc_eur, 0){% endif %} as amount_cc_eur
    from periods p
    join cycle cy on cy.company_code = p.company_code and cy.step = {{ s }}
    left join primary_cost pc on pc.version = p.version and pc.company_code = p.company_code
     and pc.period = p.period and pc.cost_centre = cy.sender
    {% if s > 1 %}left join received_{{ s }} rc on rc.version = p.version and rc.company_code = p.company_code
     and rc.period = p.period and rc.receiver = cy.sender{% endif %}
),
alloc_{{ s }} as (
    select r.version, r.company_code, r.period, {{ s }} as step, r.sender, r.receiver,
           r.key_value / sum(r.key_value) over (partition by r.version, r.company_code, r.period, r.sender) as share,
           st.amount_lc * r.key_value / sum(r.key_value) over (partition by r.version, r.company_code, r.period, r.sender) as amount_lc,
           st.amount_eur * r.key_value / sum(r.key_value) over (partition by r.version, r.company_code, r.period, r.sender) as amount_eur,
           st.amount_cc_eur * r.key_value / sum(r.key_value) over (partition by r.version, r.company_code, r.period, r.sender) as amount_cc_eur
    from receivers_{{ s }} r
    join sender_total_{{ s }} st on st.version = r.version and st.company_code = r.company_code
     and st.period = r.period and st.sender = r.sender
    where r.key_value > 0
){% if not loop.last %},{% endif %}
{% endfor %}
{% for s in range(1, max_steps + 1) %}
select * from alloc_{{ s }}{% if not loop.last %} union all{% endif %}
{% endfor %}
