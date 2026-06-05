// Auto-injected metadata for OrganizationExtract
const nodeMetadata = {
  "type": "OrganizationExtract",
  "name": "OrganizationExtract",
  "label": "Organization Extract",
  "description": "Extract editorially relevant organizations from text using an LLM.",
  "category": "extraction",
  "icon": "Building2",
  "color": "bg-amber-500",
  "requiredUpstreamNodes": [],
  "inputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    },
    {
      "id": "organizations",
      "label": "Organizations",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "prompt_file": "prompts/extract.md",
    "prompt": "# Organization Extraction Service\n\nActing as a state-of-the-art entity extraction service, identify and extract all **editorially relevant organizations** mentioned in the text provided at the end of this prompt.\n\n## Overview\n\nExtract an organization only if:\n\n1. **A specific named organization is mentioned** (agency, company, school, team, nonprofit, government body, etc.)\n2. It matters to the story's events, actions, statements, or reporting, such as:\n   - Organizations whose actions or decisions are central to the story\n   - Organizations quoted or paraphrased as sources\n   - Organizations affected by or regulating the events\n   - Employers, institutions, or agencies tied to named people **when the organization itself is editorially relevant** (not only as a person's affiliation shorthand)\n\n**IMPORTANT**: Do not extract generic institutional references without a recognizable proper-noun institution, such as \"the agency,\" \"city officials,\" \"police,\" or \"the school district\" unless the text names the specific organization (e.g. \"Chicago Police Department,\" \"Cook County State's Attorney's Office\").\n\n## Who Should NOT Be Included\n\nDo not extract:\n\n- **Individual people** — extract organizations only, never persons\n- **Generic role or staff groups without a proper institution name** — e.g. \"Cook County prosecutors\" when the story means prosecutors as a group, not a named office; \"detectives,\" \"prosecutors,\" \"coaches\" without naming the agency, department, or office\n- **Unnamed groups** — \"residents,\" \"witnesses,\" \"officials,\" \"employees\" without an organization name\n- **Places that are only geography** — a street, city, or building name is not an organization unless the story treats it as an institution (e.g. \"Wrigley Field\" as a venue operated by a named team or authority)\n- **Article authors and news outlets** when they appear only as bylines or publication credits for this article\n- **Metonyms without a proper name** — \"City Hall said\" without naming the city government body when only the metonym appears\n- **Historical, religious, mythological, or fictional entities** unless they function as real-world organizations in the story's events\n\n## Organization Identification Rules\n\n### 1. Names Required\n\nUse the **most specific conventional proper-noun name** for each organization. Organizations are generally **proper nouns** naming a specific institution—not a generic role, profession, or unnamed subset of people.\n\n- **Include** named institutions: \"Chicago Police Department,\" \"Cook County State's Attorney's Office,\" \"Brother Rice High School\"\n- **Exclude** functional or generic phrases without a proper institution: \"Cook County prosecutors\" (prosecutors as a group), \"police said\" without naming the department, \"school officials\"\n- **Include** when the text names the office or agency even if phrased functionally: \"Cook County Prosecutor's Office,\" \"the Minneapolis Park Board\"\n\n#### Expand acronyms and abbreviations\n\nWhen the full conventional name is known or clearly inferable, use the **expanded form** in `name`, not the acronym alone.\n\n- \"National Basketball Association\" not \"NBA\"\n- \"Federal Bureau of Investigation\" not \"FBI\"\n- \"National Collegiate Athletic Association\" not \"NCAA\"\n\nKeep the article's form only when expansion is ambiguous or the acronym is the story's established proper name with no clear expansion.\n\n#### High schools and campuses\n\nUse the same **school naming** logic as PlaceExtract:\n\n- Return the **full conventional school name** when inferable from context or general knowledge—not a bare city-like token or scoreline shorthand\n- In **scorelines and game summaries** (e.g. \"St. Louis Park 57 Hopkins 54\"), short tokens name **school institutions**, not the homonymous city. Prefer **Brother Rice High School**, **St. Louis Park High School**, **Hopkins High School** (or the best-known formal name), not \"Brother Rice,\" \"St. Louis Park,\" or \"Hopkins\" alone\n- When story shorthand clearly means a school (e.g. \"Park\" for St. Louis Park High School, \"Crete-Monee\" for Crete-Monee High School), return the **complete school name**\n\nSet `type` to `school` for the institution; use `sports_team` when extracting the athletic program (see below).\n\n#### Prep and college sports teams (mandatory)\n\nIn **game, score, standings, playoff, recruiting, commitment, ranking, player-stat, or other athletics** coverage, a **bare school or university name** is usually **metonymy for that school's team**—not the school as an institution and not a geography. Readers mean **which squad** (sport + gender/level), not the campus in the abstract.\n\n**Athletics signals** (any one is enough): scorelines, championships or class levels (e.g. **Class 8A champion**), positions (**quarterback**, **linebacker**, **defensive back**), recruiting ranks, commitments/decommits, season stats, coaches, schedules, team nicknames, section headers like high-school sports.\n\n**INVALID `name` values when `type` is `sports_team` (do not output these):**\n\n- Bare school shorthands in athletics context: **\"Mount Carmel\"**, **\"Mt. Carmel\"**, **\"Brother Rice\"**, **\"Marist\"**, **\"Kenwood\"**, **\"Barrington\"**, **\"Stevenson\"**, **\"New Trier\"**\n- Bare university names in game stories: **\"Duke\"**, **\"Northwestern\"**, **\"Seton Hall\"**, **\"Villanova\"** when the story is about competition—not campus policy\n- Mascot-only pro nicknames when city/market is established elsewhere in the article: **\"Cubs\"** alone when the text also establishes **Chicago**\n\n**Required pattern** — use whenever sport (and gender/level when applicable) can be inferred from **any part** of the supplied text (headline, deck, scoreline, section, caption, recurring vocabulary):\n\n`[School name as used in the story] [boys | girls | men's | women's] [sport] team`\n\nExamples:\n\n- **\"Mount Carmel football team\"** or **\"Mount Carmel High School football team\"** — not **\"Mount Carmel\"** or **\"Mount Carmel High School\"** as `school` when the story is about football players, stats, recruiting, or championships (even if \"football\" is not repeated in every sentence)\n- **\"Mount Carmel football team\"** for **\"a second Mount Carmel star\"**, **\"Class 8A champion Mount Carmel\"**, and caption lines like **\"Mount Carmel's Tavares Harrington\"** — these refer to the **team/program**, not school administration\n- **\"Brother Rice boys basketball team\"** — not **\"Brother Rice\"** in **\"Brother Rice beat Marist 48-41\"**\n- **\"Hopkins girls soccer team\"** — not **\"Hopkins\"**\n- **\"University of Minnesota men's hockey team\"** — not **\"Minnesota\"** alone in a hockey recap\n- **\"Chicago Cubs\"** — not **\"Cubs\"** or **\"Chicago\"** alone when the franchise is clearly meant\n\n**Primary sport for the entire article:** Infer the article's dominant sport (and for prep/HS/college, the dominant gender level when one clearly applies) from the headline, league, scores, coaches, and recurring vocabulary. Unless the text **explicitly** signals a different sport or level, treat **every** prep/HS/college team mention as that same sport— including opponents named once with no sport in the same sentence. Do **not** wait for the sport to appear beside each school name.\n\nIf gender level is unclear but sport is clear, use **`[School] [sport] team`**. If you cannot infer sport at all, **omit** the `sports_team` row rather than emitting a bare school name.\n\n#### Team nicknames and monikers\n\nWhen the story uses a **school's athletic nickname** instead of the school name, still emit a `sports_team` with the required pattern—not `school`, and not the nickname alone:\n\n- **\"Caravan\"** (Mount Carmel) → **\"Mount Carmel football team\"** (or **\"Mount Carmel High School football team\"**)\n- **\"Wolverines\"** (Michigan) → **\"University of Michigan football team\"** when the story is recruiting or game coverage\n- **\"Wildkits\"** (Evanston), **\"Trevians\"** (New Trier) → **`[School] football team`** (or the article's sport)\n\nMap nickname mentions to the same `sports_team` record as bare-school mentions for that program. Include **every** supporting snippet in `mentions`.\n\n**Do not** expand a nickname into a `school` row. **Do not** emit both a `school` and a `sports_team` for the same program in the same athletics story unless the text clearly treats the **campus institution** and the **competing squad** as separate actors (rare).\n\nSet `type` to `sports_team` for competing squads. Extract the **school** or **university** as `school` / `university` **only** when the **institution** (administration, district, campus policy, enrollment) is the actor—not when the story is about players, games, recruiting, or championships.\n\nWhen athletics context applies, **never** set `type` to `school` for a name that only appears beside a player, position, stat line, ranking, or championship.\n\n### 2. One Record Per Organization\n\nIf the same organization appears multiple times, emit **one** object with **all** supporting `mentions` snippets.\n\n### 3. Type Classification\n\nSet `type` to one of these slugs (use `other` when none fit):\n\n`government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`\n\n### 4. Role and Nature\n\n- **`role_in_story`**: Short phrase describing why this organization matters in the article (plain language, not codes).\n- **`nature`**: Primary editorial role — one of: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`\n- **`nature_secondary_tags`**: Optional list of additional nature values from the same vocabulary (usually 0–2 tags).\n\n### 5. Mentions\n\nEach organization must include a `mentions` array with at least one object containing:\n\n- `text` — verbatim snippet from the article\n- `quote` — `true` only when the snippet is a direct quotation attributed to the organization or its representative; otherwise `false`\n\n## Output Format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include explanatory text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_format": "{\n  \"organizations\": [\n    {\n      \"name\": \"Chicago City Hall\",\n      \"type\": \"government\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Chicago City Hall announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Brother Rice boys basketball team\",\n      \"type\": \"sports_team\",\n      \"role_in_story\": \"Won the regional semifinal\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Brother Rice beat Marist 48-41 in the regional semifinal.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Mount Carmel football team\",\n      \"type\": \"sports_team\",\n      \"role_in_story\": \"Won the conference opener\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Mount Carmel rolled past Loyola 35-14 on Friday night.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Mount Carmel football team\",\n      \"type\": \"sports_team\",\n      \"role_in_story\": \"Produced recruits committing to Michigan\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Whittingham added a second Mount Carmel star to his 2027 class when defensive back Tavares Harrington announced his commitment on Rivals' YouTube channel May 22.\",\n          \"quote\": false\n        },\n        {\n          \"text\": \"Harrington had three interceptions, six tackles for loss, a sack and 50 tackles for Class 8A champion Mount Carmel last fall.\",\n          \"quote\": false\n        },\n        {\n          \"text\": \"Less than 10 days earlier, Caravan wide receiver Quentin Burrell — ranked No. 6 in Illinois and No. 83 nationally — also committed to the Wolverines.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"National Basketball Association\",\n      \"type\": \"sports_league\",\n      \"role_in_story\": \"Announced a new policy\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"The NBA announced a new policy on Tuesday.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
} from '@/lib/nodePanelAiModel'

const DEFAULTS = {
  model: '',
  aiModelConfigId: null as string | null,
}

const MODEL_KEYS = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
} as const

function resolvedModelSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, MODEL_KEYS)
}

function hasExplicitModelChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, MODEL_KEYS)
}

interface OrganizationExtractPanelProps {
  node: any
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

function formatSampleOrganizationTitle(organization: { name?: unknown; type?: unknown }): string {
  if (typeof organization.name === 'string' && organization.name.trim()) {
    return organization.name.trim()
  }
  if (typeof organization.type === 'string' && organization.type.trim()) {
    return organization.type.trim()
  }
  return 'Organization'
}

export default function OrganizationExtractPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: OrganizationExtractPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>

  const projectId = graphContext?.projectId ?? null
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setCatalogRows([])
      setCatalogError(null)
      setCatalogLoading(false)
      return
    }
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void fetcher(['text', 'json'])
      .then((rows) => {
        if (!cancelled) {
          setCatalogRows(rows)
          setCatalogLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCatalogRows([])
          setCatalogError(e instanceof Error ? e.message : 'Could not load models.')
          setCatalogLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels])

  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])

  const resolvedUnderlying = resolvedModelSelectValue(paramsRecord, catalogRows)
  const selectionValid =
    resolvedUnderlying !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitModelChoice((node.data || {}) as Record<string, unknown>) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitModelChoice(data)) return
    const first = modelSelectOptions[0]
    if (!first) return
    const providerModelId = first.providerModelId
    const cid = first.configId ?? null
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: providerModelId,
                aiModelConfigId: cid,
              },
            }
          : n,
      ),
    )
  }, [
    editMode,
    setNodes,
    catalogLoading,
    catalogRows,
    modelSelectOptions,
    node.id,
    node.data,
  ])

  const isDisabled = !(editMode && setNodes)

  const handleModelChange = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: providerModelId,
                aiModelConfigId: configId ?? null,
              },
            }
          : n,
      ),
    )
  }

  const displayModelLabel =
    modelSelectOptions.find((o) => o.selectValue === resolvedUnderlying)?.label ??
    (showInvalidPersisted
      ? 'Previous model unavailable'
      : resolvedUnderlying !== ''
        ? String(paramsRecord.model ?? resolvedUnderlying)
        : '—')

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
    nodeOutputLookupSpec ?? undefined,
  )
  const latestData = nodeOutput || null

  return (
    <>
      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <Label className="text-sm font-medium">Input placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Pull fields from upstream JSON into the prompt using these tokens:
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — plain text or the{' '}
              <code className="bg-muted px-1 rounded">text</code> field from JSON input
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code> —{' '}
              <code className="bg-muted px-1 rounded">url</code> field
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.images}'}</code> — nested paths
              (e.g. <code className="bg-muted px-1 rounded">results.images</code>)
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption}'}</code> — one field from
              each item in an array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code> — multiple
              fields per array element
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — entire input object as JSON
            </li>
          </ul>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="settings">
        <div>
          <Label className="text-sm font-medium">Extraction model</Label>
          {editMode && setNodes ? (
            <>
              {(projectId == null || graphContext?.fetchProjectAiModels == null) && (
                <p className="text-xs text-muted-foreground mt-2">
                  Save this flow under a project to choose models your organization enabled for
                  this project.
                </p>
              )}
              {projectId != null && catalogLoading && (
                <p className="text-xs text-muted-foreground mt-2">Loading models…</p>
              )}
              {catalogError != null && catalogError !== '' ? (
                <p className="text-xs text-destructive mt-2">{catalogError}</p>
              ) : null}
              {!catalogLoading &&
                !catalogError &&
                projectId != null &&
                graphContext?.fetchProjectAiModels != null &&
                modelSelectOptions.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    No models available for this project yet. Ask an administrator to enable
                    models for your organization, then turn them on for this project in project
                    settings if needed.
                  </p>
                )}
              {showInvalidPersisted && (
                <p className="text-xs text-muted-foreground mt-2">
                  The saved model is no longer available. Choose another model below.
                </p>
              )}
              <Select
                value={radixSelectValue}
                onValueChange={handleModelChange}
                disabled={isDisabled || modelSelectOptions.length === 0}
              >
                <SelectTrigger className="h-8 text-xs mt-2">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {showInvalidPersisted ? (
                    <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                      Saved model unavailable
                    </SelectItem>
                  ) : null}
                  {modelSelectOptions.map((m) => (
                    <SelectItem key={`ox-${m.selectValue}`} value={m.selectValue}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          ) : (
            <>
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Extraction model</span>
                <span className="font-medium text-xs">{displayModelLabel}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          )}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="prompts">
        <div>
          <Label className="text-sm font-medium">Prompt</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.prompt || nodeMetadata.defaultParams?.prompt || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id ? { ...n, data: { ...n.data, prompt: e.target.value } } : n,
                  ),
                )
              }}
              placeholder="Enter custom prompt"
              className="mt-2 min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {node.data?.prompt || nodeMetadata.defaultParams?.prompt || 'Using default prompt'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">Edit extraction prompt.</p>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Output format</Label>
            <Textarea
              readOnly
              value={nodeMetadata.defaultParams?.output_format?.trim() || ''}
              placeholder="Run node sync (apps/agate-ui) after changing prompts/_output_format.json"
              className="mt-2 min-h-[120px] px-3 py-2 text-xs border border-input bg-muted/50 rounded-md font-mono cursor-default"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground mt-1">For reference only.</p>
          </div>

          {latestData && latestData.organizations && (
            <div className="border-t pt-4">
              <Label className="text-sm font-medium">Latest run</Label>
              <div className="mt-2 space-y-2">
                <div className="text-xs text-muted-foreground">
                  <div>Organizations found: {latestData.organizations.length}</div>
                </div>

                {latestData.organizations.length > 0 && (
                  <div>
                    <Label className="text-xs font-medium">Sample organizations</Label>
                    <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                      {latestData.organizations.slice(0, 3).map((organization: any, index: number) => (
                        <div key={index} className="text-xs p-2 bg-muted rounded">
                          <div className="font-medium">{formatSampleOrganizationTitle(organization)}</div>
                          {organization.role_in_story && (
                            <div className="text-muted-foreground">{organization.role_in_story}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </NodePanelTabGate>
    </>
  )
}
