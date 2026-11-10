// Smoke test against the deployed service on SAP BTP (Cloud Foundry).
//   cf create-service-key planwerk-auth smoke && cf service-key planwerk-auth smoke > key.txt
//   node scripts/btp-smoke.js <srv-url> key.txt
// Uses the client-credentials grant of the app's own XSUAA client, which holds only the
// Controller scope (xs-security.json "authorities"). Prints results, never the token or secret.
const fs = require('node:fs')

const [srv, keyFile] = process.argv.slice(2)
if (!srv || !keyFile) throw new Error('usage: node scripts/btp-smoke.js <srv-url> <service-key-file>')
const raw = fs.readFileSync(keyFile, 'utf8')
const key = JSON.parse(raw.slice(raw.indexOf('{')))
const cred = key.credentials || key

async function token() {
  const body = new URLSearchParams({ grant_type: 'client_credentials', client_id: cred.clientid, client_secret: cred.clientsecret })
  const r = await fetch(`${cred.url}/oauth/token`, { method: 'POST', body })
  if (!r.ok) throw new Error(`token request failed: ${r.status}`)
  return (await r.json()).access_token
}

const base = `${srv.replace(/\/$/, '')}/odata/v4/controlling`
const results = []
const check = (name, ok, detail) => results.push({ name, ok: Boolean(ok), detail })

async function main() {
  const anon = await fetch(`${base}/KennzahlenMonat`)
  check('anonymous request is rejected', anon.status === 401, anon.status)
  const t = await token()
  const get = async (p) => {
    const r = await fetch(`${base}/${p}`, { headers: { authorization: `Bearer ${t}` } })
    if (!r.ok) return { status: r.status, data: null }
    const txt = await r.text()
    return { status: r.status, data: p.endsWith('$count') ? txt : JSON.parse(txt) }
  }
  const kpi = await get("KennzahlenMonat?$filter=periode eq '2025-12' and bereich eq 'GRUPPE' and kennzahl eq 'db2'")
  // expected value: the same row in the initial data that was deployed (exported from the dbt semantic layer)
  const csv = fs.readFileSync(`${__dirname}/../db/data/planwerk-KennzahlenMonat.csv`, 'utf8').trim().split(/\r?\n/)
  const cols = csv[0].split(';')
  const row = csv.slice(1).map((l) => Object.fromEntries(l.split(';').map((v, i) => [cols[i], v])))
    .find((r) => r.periode === '2025-12' && r.bereich === 'GRUPPE' && r.kennzahl === 'db2')
  const got = kpi.status === 200 && kpi.data.value[0]
  check('controller reads group DB II Dec 2025, equal to the warehouse to the cent',
    got && Math.abs(Number(got.ist_eur) - Number(row.ist_eur)) < 0.005 && Math.abs(Number(got.plan_eur) - Number(row.plan_eur)) < 0.005,
    got && { ist_eur: got.ist_eur, plan_eur: got.plan_eur, expected_ist: row.ist_eur })
  const count = await get('KennzahlenMonat/$count')
  check('all KPI rows loaded into HANA', count.status === 200 && Number(count.data) === csv.length - 1, { hana: count.data, csv: csv.length - 1 })
  const br = await get("brueckeGeschlossen(jahr=2025,bis_monat=12,bereich='GRUPPE')")
  check('DB II bridge closes on HANA', br.status === 200 && br.data.geschlossen === true, br.data)
  const top = await get("topAbweichungen(jahr=2025,bis_monat=12,bereich='1000',anzahl=3)")
  check('largest unfavourable deviation is 1410', top.status === 200 && top.data.value[0].kostenstelle === '1410',
    top.data && top.data.value.map((r) => `${r.kostenstelle} ${r.abweichung_eur}`))
  const write = await fetch(`${base}/KennzahlenMonat`, { method: 'POST', headers: { authorization: `Bearer ${t}`, 'content-type': 'application/json' }, body: '{}' })
  check('service is read-only (POST refused)', write.status === 405 || write.status === 403, write.status)
  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail === undefined ? '' : '  ' + JSON.stringify(r.detail)}`)
  process.exit(results.every((r) => r.ok) ? 0 : 1)
}
main().catch((e) => { console.error(e.message); process.exit(1) })
