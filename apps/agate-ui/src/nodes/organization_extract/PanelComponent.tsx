// Auto-injected metadata for OrganizationExtract
const nodeMetadata = {
  "type": "OrganizationExtract",
  "name": "OrganizationExtract",
  "label": "Organization Extract",
  "description": "Extract editorially relevant organizations from text.",
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
    "prompt": "# Organization Extraction Service\n\nExtract every editorially relevant **organization** named in the news text at the end of this prompt. Return only valid JSON.\n\nAn organization is relevant when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, or endorsing.\n\n## Hard stops — the organization test\n\nApply this test to **every row before you emit it**: *is `name` a durable institution or organized body of people, named as a specific proper noun?* If not — or if you are unsure — **omit the row**. A missing row is always better than an organization record for a person, place, law, event, or topic. Never choose `government` or `other` just because a name acts grammatically in a sentence.\n\nNever emit as `organizations.name`:\n\n| Category | Examples | Keep instead (only when named and acting) |\n|----------|----------|-------------------------------------------|\n| Individual people | `Donald Trump`, `Ayo Dosunmu`, `Bears coach Ben Johnson`, `billionaire father of Bill Conway`, `his brother` | Their employer, team, or agency when **that institution** is the actor |\n| Bands and musical acts | `Pearl Jam`, `The Beatles`, `Alice Cooper` (the act) | Nothing — bands belong in **people** extraction |\n| Consumer brands or products alone | `Budweiser`, `Google`, `Coca-Cola`, `Twitter` as incidental platform use | `Budweiser employees union`, `Google executive team`, `Twitter` when the company itself acts (layoffs, lawsuits) |\n| Laws, programs, grants, funds, policies | `Affordable Care Act`, `Anti-Weaponization Fund`, `Full Service Community Schools grant`, `No Child Left Behind` | The administering agency (`Centers for Medicare and Medicaid Services`, `U.S. Department of Education`) |\n| Events, awards, games, historical events | `Grammy Awards`, `Super Bowl`, `World War I`, `Bud Billiken Day parade` | The organizing body (`Recording Academy`, `National Football League`) |\n| Creative works and titles | `A Mighty Wind`, `Hamilton`, `The Daily Show` (the program) | The named studio, network, production company, or presenter |\n| Publications, surveys, datasets | `American Community Survey`, `Consumer Price Index`, `Statistical Abstract` | The publishing agency (`U.S. Census Bureau`) |\n| Geography, landmarks, venues | `Grant Park`, `Kenwood`, `Anne Frank House`, `Arc de Triomphe`, `the Chicago area`, `downtown` | The governing or operating body (`Grant Park Advisory Council`, `Kenwood Academy High School`) |\n| Broad descriptors and role groups | `American civil society`, `Arizona families`, `Arizona grand jury`, `prosecutors`, `Area 5 detectives`, `residents`, `officials` | A named office or department (`Chicago Police Department`) |\n| Generic public-service groups or laws with geography | `Illinois police departments`, `Illinois DMVs`, `Illinois state law`, `state courts`, `local schools` | A specific named body (`Chicago Police Department`, `Illinois Secretary of State`, `Illinois Supreme Court`) |\n| Concepts, industries, topics | `artificial intelligence`, `climate change`, `inflation`, `social media` | Nothing — even when capitalized or central to the story |\n| Metonyms with no named body | `\"City Hall said\"` with no named government body | The named body when the text provides one |\n\nSkip generic references without a named institution (\"the agency,\" \"police,\" \"school officials,\" \"Illinois police departments,\" \"Illinois state law\"); article bylines and publication credits; and historical, religious, or fictional entities unless they act as real-world organizations in the story.\n\n## Borderline cousins\n\nThe same name can be an organization, a brand, a work/title, a venue, or an event — use context. When a borderline mention is editorially relevant, include the row with the best normal `type` and set `organization_boundary`:\n\n- `borderline_brand_platform` — a **named corporate or platform entity** is acting but context is ambiguous (never a bare consumer brand with no organized body)\n- `borderline_work_title` — column, show, book, film, franchise, or publication title (\"Dear Abby answered a reader\")\n- `borderline_place_business` — business name may be only a location (\"the event happened at Baskin Robbins\")\n- `borderline_event_competition` — an organizing body might exist but context is ambiguous; if the mention is just the event or award name, **omit** instead\n\nOmit `organization_boundary` for clear organizations, and never use `other` just because a row is borderline.\n\nExamples:\n- \"Twitter laid off 20 people\" → organization (`company`); \"Joe sent a message on Twitter\" → omit\n- \"Budweiser employees union voted to strike\" → organization; \"Budweiser\" as a product mention → omit\n- \"AMC announced it would close two theaters\" → organization (`company`)\n\n## Names\n\n- Use the most specific conventional proper-noun name; expand acronyms when known (`National Basketball Association`, not `NBA`) unless expansion is ambiguous.\n- One record per organization; merge all `mentions`.\n- **Schools:** always the full school name (`Brother Rice High School`), never a bare scoreline token (`Belvidere`, `Woodstock`, `Park`) — expand with your world knowledge to the conventional full name.\n- **Sports teams:** in athletics coverage, bare school or university names mean the **team**. Use `sports_team` with the pattern `[School] [boys|girls|men's|women's] [sport] team` when the sport is inferable. Map nicknames (\"Caravan,\" \"Wolverines\") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor.\n- **Prep scorelines (all formats):** tokens in game results, schedules, or box scores (`Belvidere 55, Woodstock 53`, `Team A at Team B`) name **school teams**, not the homonymous cities. **Extract both sides**, expanded to full school team names (`Belvidere High School boys basketball team`). Use dateline, league, and sport section to infer state and sport.\n- **Pro and college teams before player names:** when a team nickname precedes a player or role (`Phillies masher Kyle Schwarber`, `Cubs ace`), extract the team as `sports_team` with the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`) even when the team is not the grammatical subject.\n\n## Fields\n\n### type\n\nOne slug: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`\n\n**`other` is not a catch-all.** Use it only for a named institution that is genuinely organizational but outside the list. If you would choose `other` only because nothing fits — or the mention is a law, place, concept, or topic — **omit the row** instead.\n\n### role_in_story\n\nShort plain-language reason the organization matters in this article.\n\n### nature\n\nOne of: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`\n\n### nature_secondary_tags\n\nOptional 0–2 additional tags from the same vocabulary.\n\n### mentions\n\nAt least one object per organization with `text` (verbatim snippet) and `quote` (true only for direct quotations). Prefer a full sentence or paragraph containing the organization — not the name alone unless the name is the entire sentence.\n\n## Output\n\nReturn **only** valid JSON. No text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_mode": "compact",
    "output_format": "{\n  \"organizations\": [\n    {\n      \"name\": \"Chicago City Hall\",\n      \"type\": \"government\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Chicago City Hall announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Brother Rice boys basketball team\",\n      \"type\": \"sports_team\",\n      \"role_in_story\": \"Won the regional semifinal\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Brother Rice beat Marist 48-41 in the regional semifinal.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Dear Abby\",\n      \"type\": \"media\",\n      \"organization_boundary\": \"borderline_work_title\",\n      \"role_in_story\": \"Advice column central to the story\",\n      \"nature\": \"source\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Dear Abby advised the reader to seek counseling.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"National Basketball Association\",\n      \"type\": \"sports_league\",\n      \"role_in_story\": \"Announced a new policy\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"The NBA announced a new policy on Tuesday.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
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
  const latestData = (nodeOutput as { organizations?: unknown[] } | null | undefined) || null

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
