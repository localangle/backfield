/** Read/write person fields during Agate people review. */

export type PersonEditFields = {
  name: string
  title: string
  affiliation: string
  personType: string
  roleInStory: string
  nature: string
  publicFigure: boolean
}

function cloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

export function readPersonEditFields(
  person: Record<string, unknown> | null | undefined,
): PersonEditFields {
  if (!person || typeof person !== 'object') {
    return {
      name: '',
      title: '',
      affiliation: '',
      personType: '',
      roleInStory: '',
      nature: '',
      publicFigure: false,
    }
  }
  return {
    name: typeof person.name === 'string' ? person.name.trim() : '',
    title: typeof person.title === 'string' ? person.title.trim() : '',
    affiliation: typeof person.affiliation === 'string' ? person.affiliation.trim() : '',
    personType: typeof person.type === 'string' ? person.type.trim() : '',
    roleInStory: typeof person.role_in_story === 'string' ? person.role_in_story.trim() : '',
    nature: typeof person.nature === 'string' ? person.nature.trim() : '',
    publicFigure: Boolean(person.public_figure),
  }
}

export function personEditFieldsEqual(a: PersonEditFields, b: PersonEditFields): boolean {
  return (
    a.name === b.name &&
    a.title === b.title &&
    a.affiliation === b.affiliation &&
    a.personType === b.personType &&
    a.roleInStory === b.roleInStory &&
    a.nature === b.nature &&
    a.publicFigure === b.publicFigure
  )
}

export function applyPersonEditFields(
  person: Record<string, unknown>,
  fields: PersonEditFields,
): Record<string, unknown> {
  const out = cloneJson(person) as Record<string, unknown>
  out.name = fields.name.trim()
  out.title = fields.title.trim()
  out.affiliation = fields.affiliation.trim()
  out.type = fields.personType.trim()
  out.role_in_story = fields.roleInStory.trim()
  out.nature = fields.nature.trim()
  out.public_figure = fields.publicFigure
  return out
}

export function buildPersonEditOverlayPatch(fields: PersonEditFields): Record<string, unknown> {
  return {
    name: fields.name.trim(),
    title: fields.title.trim(),
    affiliation: fields.affiliation.trim(),
    type: fields.personType.trim(),
    role_in_story: fields.roleInStory.trim(),
    nature: fields.nature.trim(),
    public_figure: fields.publicFigure,
  }
}
