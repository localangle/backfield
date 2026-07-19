import type { ReactNode } from "react"
import MetaQueryBuilder from "./MetaQueryBuilder"
import IdTypeahead from "./IdTypeahead"
import type { OpenApiSchema } from "../lib/openapi"
import type { FieldPresentation } from "../lib/presentation"

interface ParameterFieldProps {
  apiKey: string
  entityType?: string
  id: string
  name: string
  origin: string
  presentation: FieldPresentation
  projectSlug: string
  required?: boolean
  schema?: OpenApiSchema
  value: string
  wide?: boolean
  onChange: (value: string) => void
}

function selectedValues(value: string): Set<string> {
  return new Set(
    value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean),
  )
}

export default function ParameterField({
  apiKey,
  entityType,
  id,
  name,
  origin,
  presentation,
  projectSlug,
  required,
  schema,
  value,
  wide,
  onChange,
}: ParameterFieldProps) {
  const descriptionId = `${id}-description`
  const describedBy = presentation.helperText ? descriptionId : undefined
  const checkboxValues = selectedValues(value)

  let control: ReactNode
  if (presentation.control === "typeahead" && presentation.typeaheadKind) {
    control = (
      <IdTypeahead
        id={id}
        kind={presentation.typeaheadKind}
        origin={origin}
        projectSlug={projectSlug}
        apiKey={apiKey}
        entityType={entityType}
        required={required}
        value={value}
        placeholder={presentation.placeholder}
        onChange={onChange}
      />
    )
  } else if (presentation.control === "meta-builder") {
    control = (
      <MetaQueryBuilder
        origin={origin}
        projectSlug={projectSlug}
        apiKey={apiKey}
        value={value}
        onChange={onChange}
      />
    )
  } else if (presentation.control === "checkboxes") {
    control = (
      <div className="parameter-checkboxes" id={id} aria-describedby={describedBy}>
        {presentation.options?.map((option) => (
          <label key={option.value} className="parameter-checkbox">
            <input
              type="checkbox"
              checked={checkboxValues.has(option.value)}
              onChange={(event) => {
                const next = new Set(checkboxValues)
                if (event.target.checked) next.add(option.value)
                else next.delete(option.value)
                onChange([...next].join("\n"))
              }}
            />
            <span>{option.label}</span>
          </label>
        ))}
        {!presentation.options?.length && (
          <span className="field-description">
            {presentation.emptyLabel ?? "No choices available"}
          </span>
        )}
      </div>
    )
  } else if (presentation.control === "select") {
    control = (
      <select
        id={id}
        value={value}
        required={required}
        disabled={presentation.disabled}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">
          {required
            ? presentation.emptyLabel ?? "Select a value"
            : presentation.emptyLabel ?? "Any"}
        </option>
        {Array.from(
          new Set(
            presentation.options
              ?.map((option) => option.group)
              .filter((group): group is string => Boolean(group)),
          ),
        ).map((group) => (
          <optgroup key={group} label={group}>
            {presentation.options
              ?.filter((option) => option.group === group)
              .map((option) => (
                <option key={`${group}:${option.value}`} value={option.value}>
                  {option.label}
                </option>
              ))}
          </optgroup>
        ))}
        {presentation.options
          ?.filter((option) => !option.group)
          .map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
      </select>
    )
  } else if (presentation.control === "textarea") {
    control = (
      <textarea
        id={id}
        value={value}
        required={required}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value)}
        placeholder={presentation.placeholder}
        rows={name === "inputs" ? 6 : 3}
        spellCheck={name !== "inputs"}
      />
    )
  } else {
    control = (
      <input
        id={id}
        value={value}
        required={required}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value)}
        placeholder={presentation.placeholder}
        type={presentation.control}
        min={schema?.minimum}
        max={schema?.maximum}
        minLength={schema?.minLength}
        maxLength={schema?.maxLength}
        pattern={schema?.pattern}
        step={schema?.type === "integer" ? 1 : undefined}
      />
    )
  }

  return (
    <div
      className={`field parameter-field ${
        wide || presentation.wide ? "parameter-field-wide" : ""
      }`}
    >
      <label htmlFor={presentation.control === "meta-builder" ? undefined : id}>
        <span className="field-name">
          {name}
          {required && (
            <span className="required-mark" aria-hidden>
              *
            </span>
          )}
        </span>
        <span className="field-meta">
          {presentation.typeLabel}
          {required && <span className="required-badge">Required</span>}
        </span>
      </label>
      <div className="parameter-control">{control}</div>
      <div className="parameter-description-slot">
        {presentation.helperText ? (
          <p id={descriptionId} className="field-description">
            {presentation.helperText}
          </p>
        ) : null}
      </div>
    </div>
  )
}
