// Run: npm test  (node:test + @cap-js/cds-test, SQLite in memory, mocked users from package.json)
const { describe, it } = require('node:test')
const assert = require('node:assert/strict')
const cds = require('@sap/cds')

const { GET } = cds.test(__dirname + '/..')
const base = '/odata/v4/controlling'
const as = (user) => ({ auth: { username: user, password: '' } })

describe('Planwerk ControllingService', () => {
  it('rejects anonymous access', async () => {
    await assert.rejects(GET(`${base}/KennzahlenMonat`), /401/)
  })

  it('controller reads the group DB II for December 2025', async () => {
    const { data } = await GET(`${base}/KennzahlenMonat?$filter=periode eq '2025-12' and bereich eq 'GRUPPE' and kennzahl eq 'db2'`, as('controller'))
    assert.equal(data.value.length, 1)
    assert.ok(Number(data.value[0].plan_eur) > 0)
  })

  it('cost-centre owner sees only own cost centres', async () => {
    const { data } = await GET(`${base}/Kostenstellen?$filter=jahr eq 2025 and bis_monat eq 12`, as('leitung_instandhaltung'))
    assert.ok(data.value.length > 0)
    assert.deepEqual([...new Set(data.value.map((r) => r.kostenstelle))], ['1410'])
  })

  it('cost-centre owner cannot read the group KPIs', async () => {
    await assert.rejects(GET(`${base}/KennzahlenMonat`, as('leitung_instandhaltung')), /403/)
  })

  it('user without role is refused', async () => {
    await assert.rejects(GET(`${base}/Kostenstellen`, as('gast')), /403/)
  })

  it('DB II bridge closes for the group, full year 2025', async () => {
    const { data } = await GET(`${base}/brueckeGeschlossen(jahr=2025,bis_monat=12,bereich='GRUPPE')`, as('controller'))
    assert.equal(data.geschlossen, true)
  })

  it('top deviations respect the owner restriction', async () => {
    // the owner of 1410 sees only 1410
    const own = await GET(`${base}/topAbweichungen(jahr=2025,bis_monat=12,bereich='1000',anzahl=10)`, as('leitung_instandhaltung'))
    assert.deepEqual(own.data.value.map((r) => r.kostenstelle), ['1410'])
    const pl = await GET(`${base}/topAbweichungen(jahr=2025,bis_monat=12,bereich='3000',anzahl=10)`, as('controller'))
    assert.ok(pl.data.value.length > 1) // the controller also sees the Polish cost centres
    // 1500 and 1520 were below plan (favourable): nothing to report for that owner
    const pumps = await GET(`${base}/topAbweichungen(jahr=2025,bis_monat=12,bereich='1000',anzahl=10)`, as('leitung_fertigung_pumpen'))
    assert.equal(pumps.data.value.length, 0)
  })

  it('largest unfavourable deviation for the controller is cost centre 1410 (one-off repair)', async () => {
    const { data } = await GET(`${base}/topAbweichungen(jahr=2025,bis_monat=12,bereich='1000',anzahl=1)`, as('controller'))
    assert.equal(data.value[0].kostenstelle, '1410')
  })
})
