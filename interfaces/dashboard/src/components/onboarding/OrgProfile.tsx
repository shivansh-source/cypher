import { ENTITY_TYPES, frameworkLabel, frameworksForEntity, type EntityType } from "@/lib/frameworks";

/**
 * The setup screen's "Your organisation" section: a name, what kind of
 * regulated entity it is, and — once a kind is chosen — which of the control
 * library's frameworks Cypher will map its findings to.
 */
export function OrgProfile({
  name,
  entityType,
  onName,
  onEntityType,
}: {
  name: string;
  entityType: EntityType | null;
  onName: (name: string) => void;
  onEntityType: (type: EntityType) => void;
}) {
  const frameworks = entityType ? frameworksForEntity(entityType) : null;

  return (
    <section className="ob-org" aria-labelledby="ob-org-h">
      <div className="ob-head">
        <h2 id="ob-org-h">Your organisation</h2>
        <p>Used to name your workspace and pick the regulations your findings are mapped to.</p>
      </div>

      <label className="ob-field">
        <span className="ob-field-label">Organisation name</span>
        <input
          type="text"
          value={name}
          maxLength={80}
          autoComplete="organization"
          placeholder="e.g. LoanEase Finance"
          onChange={(event) => onName(event.target.value)}
        />
      </label>

      <fieldset className="ob-kind">
        <legend className="ob-field-label">What kind of organisation is it?</legend>
        <div className="ob-kind-opts">
          {ENTITY_TYPES.map((type) => (
            <label key={type.id} className={`ob-kind-opt${entityType === type.id ? " on" : ""}`}>
              <input
                type="radio"
                name="entity-type"
                className="sr-only"
                checked={entityType === type.id}
                onChange={() => onEntityType(type.id)}
              />
              <b>{type.label}</b>
              <span>{type.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {frameworks ? (
        <div className="ob-fw" key={entityType} aria-live="polite">
          <p className="ob-field-label">Cypher will map your findings to</p>
          <ul className="ob-chips">
            {frameworks.mandatory.map((key) => (
              <li key={key} className="ob-chip">
                {frameworkLabel(key)}
              </li>
            ))}
            {frameworks.voluntary.map((key) => (
              <li key={key} className="ob-chip soft">
                {frameworkLabel(key)} <span>voluntary</span>
              </li>
            ))}
          </ul>
          {frameworks.note ? <p className="ob-note">{frameworks.note}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
