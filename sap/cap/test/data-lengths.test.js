// SQLite does not enforce String(n); HANA does. Check every initial-data value against its column length.
const { describe, it } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const cds = require('@sap/cds')

describe('initial data fits the HANA column lengths', () => {
  it('no CSV value is longer than its String(n) element', async () => {
    const csn = await cds.load(path.join(__dirname, '../db'))
    const dir = path.join(__dirname, '../db/data')
    const problems = []
    for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.csv'))) {
      const entity = csn.definitions[file.replace('.csv', '').replace('-', '.')]
      assert.ok(entity, `no entity for ${file}`)
      const [header, ...rows] = fs.readFileSync(path.join(dir, file), 'utf8').trim().split(/\r?\n/)
      const cols = header.split(';')
      for (const row of rows) {
        row.split(';').forEach((v, i) => {
          const el = entity.elements[cols[i]]
          if (el && el.type === 'cds.String' && el.length && v.length > el.length) {
            problems.push(`${file} ${cols[i]}='${v}' (${v.length} > ${el.length})`)
          }
        })
      }
    }
    assert.deepEqual([...new Set(problems)], [])
  })
})
