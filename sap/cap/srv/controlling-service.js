const cds = require('@sap/cds')

module.exports = class ControllingService extends cds.ApplicationService {
  init() {
    const { Kostenstellen, Abweichungsbruecke } = this.entities

    this.on('topAbweichungen', async (req) => {
      const { jahr, bis_monat, bereich = '1000', anzahl = 5 } = req.data
      if (!jahr || !bis_monat) return req.reject(400, 'jahr und bis_monat sind Pflicht')
      if (anzahl < 1 || anzahl > 50) return req.reject(400, 'anzahl muss zwischen 1 und 50 liegen')
      // Querying through the service entity applies the @restrict where-clause of the caller.
      return this.run(
        SELECT.from(Kostenstellen)
          .columns('kostenstelle', 'kostenstelle_text', 'plan_eur', 'ist_eur', 'abweichung_eur')
          .where({ jahr, bis_monat, bereich })
          .and('abweichung_eur <', 0)
          .orderBy('abweichung_eur asc')
          .limit(anzahl)
      )
    })

    this.on('brueckeGeschlossen', async (req) => {
      const { jahr, bis_monat, bereich = 'GRUPPE' } = req.data
      const b = await this.run(SELECT.one.from(Abweichungsbruecke).where({ jahr, bis_monat, bereich }))
      if (!b) return req.reject(404, `Keine Brücke für ${bereich} ${jahr}/${bis_monat}`)
      const effekte = ['mengeneffekt_eur', 'mixeffekt_eur', 'preiseffekt_eur', 'materialkosteneffekt_eur',
        'erloesschmaelerung_eur', 'fixkosteneffekt_db2_eur', 'waehrungseffekt_eur']
      const summe = effekte.reduce((s, k) => s + Number(b[k]), 0)
      const rest = Math.round((summe - (Number(b.ist_db2_eur) - Number(b.plan_db2_eur))) * 100) / 100
      return { rest_eur: rest, geschlossen: Math.abs(rest) < 0.01 * effekte.length }
    })

    return super.init()
  }
}
