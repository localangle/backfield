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
    "prompt": "# Organization Extraction Service\n\nExtract **editorially relevant organizations** from the text at the end of this prompt.\n\n## When to extract\n\nExtract a named organization when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, endorsing, or similar.\n\nRequire a **specific proper-noun institution** (agency, company, school, team, nonprofit, government body, etc.). Skip generic references without a named institution (\"the agency,\" \"police,\" \"school officials\") unless the text names the office (\"Chicago Police Department,\" \"Cook County State's Attorney's Office\").\n\n## Do not extract\n\n- Individual people\n- **Named human individuals** — coaches, players, athletes, elected officials, artists, musicians, executives, sources, witnesses, and other people quoted or acting in the story are **people**, not organizations (e.g. `\"Bears coach Ben Johnson said…\"` → person **Ben Johnson**; **Alice Cooper** on a roster with **Marc Ribot** and **Steve Earle** → people). Extract their **employer, team, or agency** only when **that institution** is the accountable actor in the story—not the person's personal name.\n- **Descriptive or relational person phrases** — omit entirely when the text describes a **person's relationship, wealth, or role** rather than naming an institution (e.g. `\"billionaire father of Bill Conway\"`, `\"his brother\"`, `\"the victim's mother\"`). These are not organizations.\n- Generic staff or role groups without a named institution (\"prosecutors,\" \"coaches,\" \"detectives\")\n- Unnamed groups (\"residents,\" \"witnesses,\" \"officials\")\n- Geography-only places (street, city, building) unless the story treats them as institutions\n- Article bylines or publication credits only\n- Metonyms without a proper name (\"City Hall said\" with no named government body)\n- Historical, religious, mythological, or fictional entities unless they act as real-world organizations in the story\n\n## Close cousins (brands, works, venues, events)\n\nThe same name can be an organization, a brand, a work/title, a venue, or an event. Use context.\n\n**Clear organization** — extract normally when people, management, employees, ownership, policy, statements, lawsuits, layoffs, operations, hiring, closures, or organized activity are in view.\n\n**Omit** — when the name is only incidental product, platform, service, venue, title, or event context and does not matter to the story.\n\n**Borderline but editorially relevant** — include the row, use the best normal `type`, and set `organization_boundary` to one of:\n- `borderline_brand_platform` — brand/platform/service use may not be organizational (\"sent a message on Twitter\")\n- `borderline_work_title` — column, show, book, film, franchise, publication title, etc. (\"Dear Abby answered a reader\")\n- `borderline_place_business` — business name may be only a location (\"the event happened at Baskin Robbins\")\n- `borderline_event_competition` — named event/competition may not be an organizing body (\"Lollapalooza drew 100,000 people\")\n\nDo **not** use `other` just because a row is borderline. Omit `organization_boundary` for clear organizations.\n\nExamples:\n- \"Twitter laid off 20 people\" → organization (`company`)\n- \"Joe sent a message on Twitter\" → omit (incidental platform use)\n- \"AMC announced it would close two theaters\" → organization\n- \"Baskin Robbins employees gathered\" → organization (`local_business`)\n- \"The event happened at Baskin Robbins\" → omit unless the business itself matters; if editorially relevant but venue-like, `borderline_place_business`\n\n## Names and types\n\n- Use the most specific conventional proper-noun name.\n- `name` must identify an **institution or group**, not an individual human's given and family name (see **Do not extract**). When unsure whether a proper noun is a person or an organization, **omit it from organizations** if the text treats them as an individual acting, speaking, or being described.\n- Expand acronyms when known (\"National Basketball Association\" not \"NBA\") unless expansion is ambiguous.\n- **Schools:** use full school names in scorelines, not bare city tokens (\"Brother Rice High School,\" not \"Brother Rice\" alone when naming a school institution). **Never** put a bare scoreline token alone in `name` (not `\"Belvidere\"`, `\"Woodstock\"`, `\"Smith\"`, `\"Park\"`)—expand with your world knowledge to the conventional **full school name** (`Belvidere High School`, `Woodstock High School`, `Smith High School`).\n- **Sports teams:** in athletics coverage, bare school/university names usually mean the **team**, not the campus. Use `sports_team` with pattern `[School] [boys|girls|men's|women's] [sport] team` when sport is inferable from the article. Never emit bare \"Mount Carmel,\" \"Brother Rice,\" or \"Cubs\" alone as `sports_team`. Map nicknames (\"Caravan,\" \"Wolverines\") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor—not players, games, recruiting, or championships.\n- **Prep scorelines (all formats):** when a token appears in a **game result or schedule**—final scores (`St. Louis Park 57 Hopkins 54`, `Belvidere 55, Woodstock 53`, `Brother Rice 48 Marist 41`), scheduled matchups (`Team A at Team B`), or box-score tables—it names a **school team**, not the homonymous city. **Extract both sides.** Expand each token to the full school name plus team when sport is clear (e.g. `Belvidere 55, Woodstock 53` in basketball coverage → `Belvidere High School boys basketball team`, `Woodstock High School boys basketball team`; not `Belvidere` or `Woodstock` alone, and not `school` when the story is about a game). Use dateline, league, sport section, and nearby context to infer state and sport; apply conventional local school names when you know them.\n- **Pro and college teams before player names:** when a team nickname precedes a player, coach, or role descriptor (`Phillies masher Kyle Schwarber`, `Cubs ace`, `Yankees outfielder`), extract the team as `sports_team` using the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`, `New York Yankees`) even if the team is not the grammatical subject of the sentence.\n- One record per organization; merge all `mentions`.\n- `type` slugs: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`\n- `role_in_story`: short plain-language reason it matters\n- `nature`: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`\n- `nature_secondary_tags`: optional 0–2 tags from the same nature vocabulary\n- `mentions`: at least one object with `text` (verbatim snippet) and `quote` (true only for direct quotations) per organization. Prefer a full **sentence or paragraph** containing the organization—not the organization name alone unless the name is the entire sentence.\n\n## Output\n\nReturn **only** valid JSON. No text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_mode": "compact",
    "output_format": "{\n  \"organizations\": [\n    {\n      \"name\": \"Chicago City Hall\",\n      \"type\": \"government\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Chicago City Hall announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Brother Rice boys basketball team\",\n      \"type\": \"sports_team\",\n      \"role_in_story\": \"Won the regional semifinal\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Brother Rice beat Marist 48-41 in the regional semifinal.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Dear Abby\",\n      \"type\": \"media\",\n      \"organization_boundary\": \"borderline_work_title\",\n      \"role_in_story\": \"Advice column central to the story\",\n      \"nature\": \"source\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Dear Abby advised the reader to seek counseling.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"National Basketball Association\",\n      \"type\": \"sports_league\",\n      \"role_in_story\": \"Announced a new policy\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"The NBA announced a new policy on Tuesday.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

interface OrganizationExtractData {
  model?: string
}

function OrganizationExtractNode({ data, selected }: NodeProps<OrganizationExtractData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('OrganizationExtract', 'h-4 w-4')
  const bgColor = getNodeBgColor('OrganizationExtract')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Organization Extract
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
        <div className="text-xs space-y-2">
          {requiredUpstreamNodes.length > 0 && (
            <div className="space-y-1">
              <Label className="text-muted-foreground">Depends on:</Label>
              <div className="flex flex-wrap gap-2">
                {requiredUpstreamNodes.map((nodeType: string) => {
                  const depIcon = getNodeIcon(nodeType, 'h-3 w-3')
                  const label = getNodeLabel(nodeType)
                  return (
                    <div key={nodeType} className="flex items-center gap-1">
                      {depIcon}
                      <span className="text-xs">{label}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {dependencyHelperText && <p className="text-xs text-muted-foreground mt-1">{dependencyHelperText}</p>}
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="organizations"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(OrganizationExtractNode)
