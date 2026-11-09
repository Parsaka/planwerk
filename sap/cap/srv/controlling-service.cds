using planwerk as db from '../db/schema';

/**
 * Read-only controlling service (OData V4 at /odata/v4/controlling).
 * Roles (xs-security.json):
 *   Controller       - all company codes and cost centres
 *   CostCentreOwner  - only own cost centres (user attribute "kostenstelle"),
 *                      the same rule as the Snowflake row access policy and the AI assistant.
 */
@requires: 'authenticated-user'
@readonly
service ControllingService {

  @restrict: [{ grant: 'READ', to: 'Controller' }]
  entity KennzahlenMonat    as projection on db.KennzahlenMonat;

  @restrict: [{ grant: 'READ', to: 'Controller' }]
  entity Abweichungsbruecke as projection on db.Abweichungsbruecke;

  @restrict: [{ grant: 'READ', to: 'Controller' }]
  entity Produktgruppen     as projection on db.Produktgruppen;

  @restrict: [{ grant: 'READ', to: 'Controller' }]
  entity Auftragseingang    as projection on db.Auftragseingang;

  @restrict: [
    { grant: 'READ', to: 'Controller' },
    { grant: 'READ', to: 'CostCentreOwner', where: 'kostenstelle = $user.kostenstelle' }
  ]
  entity Kostenstellen      as projection on db.Kostenstellen;

  @restrict: [
    { grant: 'READ', to: 'Controller' },
    { grant: 'READ', to: 'CostCentreOwner', where: 'kostenstelle = $user.kostenstelle' }
  ]
  entity Kostenarten        as projection on db.Kostenarten;

  /** Largest unfavourable cost-centre deviations (Ist above Plan) in one company code (bereich, default 1000), respecting the caller's rights. */
  @restrict: [{ to: ['Controller', 'CostCentreOwner'] }]
  function topAbweichungen(jahr : Integer, bis_monat : Integer, bereich : String, anzahl : Integer)
    returns array of {
      kostenstelle      : String;
      kostenstelle_text : String;
      plan_eur          : Decimal(17, 2);
      ist_eur           : Decimal(17, 2);
      abweichung_eur    : Decimal(17, 2);
    };

  /** DB II bridge closes: sum of effects equals Ist - Plan (to the cent). */
  @restrict: [{ to: 'Controller' }]
  function brueckeGeschlossen(jahr : Integer, bis_monat : Integer, bereich : String)
    returns { rest_eur : Decimal(17, 2); geschlossen : Boolean; };
}
