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
    "prompt": "# Organization Extraction Service\n\nExtract **editorially relevant organizations** from the text at the end of this prompt.\n\n## Organization decision gate\n\nBefore adding any row, ask: **Is this a durable institution or organized body of people?**\n\nExtract only when the answer is yes. If the name is primarily a **person, place, law, program, grant, fund, event, award, historical event, film/performance/show title, publication or survey title, landmark or building, broad social descriptor, work/title, topic, or generic role group**, **omit it** from `organizations`.\n\nRequire a **specific proper-noun institution**—not a broad descriptor, demographic phrase, or generic category label (`American civil society`, `Arizona families`, `Arizona grand jury`).\n\nNever choose `government` or `other` just because the name acts grammatically in a sentence. A law, park, person, film title, or event is still not an organization.\n\nPaired examples:\n- omit `Grant Park`; keep `Grant Park Advisory Council`\n- omit `Kenwood`; keep `Kenwood Academy High School`\n- omit `Affordable Care Act`; keep `Centers for Medicare and Medicaid Services` when that agency is named and acting\n- omit `Anti-Weaponization Fund`; keep the **administering agency or office** only when that institution is named and acting\n- omit `Grammy Awards`; keep `Recording Academy` when that body is named and acting\n- omit `Donald Trump`, `Antonio Martínez Ocasio`, `Ayo Dosunmu`; keep `Trump administration` only when the administration is the accountable actor\n- omit `Area 5 detectives`; keep `Chicago Police Department` or `Chicago Police Department Area 5 Detectives` when the institution is named\n- omit `A Mighty Wind`, `Angelo, My Love`; keep a **named production company, studio, or presenter** only when that institution is the actor\n- omit `American Community Survey`; keep `U.S. Census Bureau` when that agency is named and acting\n- omit `Anne Frank House`, `Arc de Triomphe`; keep a **named museum foundation or operating institution** only when that body is the actor—not the landmark name alone\n- omit `American civil society`, `Arizona families`, `Arizona grand jury`; keep a **named office, agency, or committee** only when the institution is explicit\n\n## When to extract\n\nExtract a named organization when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, endorsing, or similar.\n\nRequire a **specific proper-noun institution** (agency, company, school, team, nonprofit, government body, etc.). Skip generic references without a named institution (\"the agency,\" \"police,\" \"school officials\") unless the text names the office (\"Chicago Police Department,\" \"Cook County State's Attorney's Office\").\n\n## Do not extract\n\n- Individual people\n- **Named human individuals** — coaches, players, athletes, elected officials, artists, musicians, actors, executives, sources, witnesses, and other people quoted or acting in the story are **people**, not organizations (e.g. `\"Bears coach Ben Johnson said…\"` → person **Ben Johnson**; **Alice Cooper** on a roster with **Marc Ribot** and **Steve Earle** → people; **Antonio Martínez Ocasio**, **Ayo Dosunmu** → people). Extract their **employer, team, or agency** only when **that institution** is the accountable actor in the story—not the person's personal name.\n- **Descriptive or relational person phrases** — omit entirely when the text describes a **person's relationship, wealth, or role** rather than naming an institution (e.g. `\"billionaire father of Bill Conway\"`, `\"his brother\"`, `\"the victim's mother\"`). These are not organizations.\n- Generic staff or role groups without a named institution (\"prosecutors,\" \"coaches,\" \"detectives,\" `Area 5 detectives`, `Chicago Bulls coach Billy Donovan`)\n- Unnamed groups (\"residents,\" \"witnesses,\" \"officials\")\n- Geography-only places (street, city, neighborhood, building, **landmark, monument, historic site, museum building, region, or area**) unless the story names an **institutional body** that governs or operates there—e.g. omit **Grant Park**, **Kenwood**, **Arc de Triomphe**, **Anne Frank House**, **the Chicago area**, **downtown**, **the lakefront**; keep **Evanston City Council**, **Grant Park Advisory Council**\n- **Films, performances, shows, albums, books, and other creative works** named as titles—not organizations (`A Mighty Wind`, `Angelo, My Love`, `Hamilton`, `The Daily Show` as a program title). Extract a **named studio, network, production company, or presenter** only when that institution is the accountable actor—not the title alone\n- **Publications, surveys, reports, and datasets** named as titles or products—not organizations (`American Community Survey`, `Consumer Price Index`, `Statistical Abstract`). Extract the **publishing agency, bureau, or company** only when that institution is named and acting\n- **Broad descriptors and generic social categories** that are not proper-noun institutions (`American civil society`, `Arizona families`, `Arizona grand jury`, `local residents`, `the business community`). These are topics or groups, not organizations—omit unless a **named institution** is explicit\n- **Laws, statutes, acts, bills, regulations, programs, grants, funds, and policies** named as rules or coverage topics—not organizations (`Affordable Care Act`, `Administrative Procedure Act`, `Anti-Weaponization Fund`, `Full Service Community Schools grant`, `No Child Left Behind`, `the tax bill`). Extract an **administering agency or department** only when that **institution** is named and acts (`Centers for Medicare and Medicaid Services`, `U.S. Department of Education`)—not the law, program, or fund title alone\n- **Events, awards, competitions, concerts, festivals, parades, games, and historical events** (`Grammy Awards`, `Super Bowl`, `World War I`, `Bud Billiken Day parade`) unless the story names the **organizing institution** (`Recording Academy`, `National Football League`) as the accountable actor\n- **Concepts, technologies, industries, and abstract topics** without a named institution (`artificial intelligence`, `climate change`, `inflation`, `social media`)—omit; they are not organizations even when capitalized or central to the story\n- Article bylines or publication credits only\n- Metonyms without a proper name (\"City Hall said\" with no named government body)\n- Historical, religious, mythological, or fictional entities unless they act as real-world organizations in the story\n\n## Close cousins (brands, works, venues, events)\n\nThe same name can be an organization, a brand, a work/title, a venue, or an event. Use context.\n\n**Clear organization** — extract normally when people, management, employees, ownership, policy, statements, lawsuits, layoffs, operations, hiring, closures, or organized activity are in view.\n\n**Omit** — when the name is only incidental product, platform, service, venue, title, event context, **geography, law/policy, grant/program, or abstract topic** and does not matter to the story—or when there is **no accountable group of people** behind the name. For awards, games, concerts, festivals, parades, and historical events, **omit the event name** unless the organizing institution is clearly the actor.\n\nExamples of **omit** (not organizations):\n- `\"the Affordable Care Act\"` / `\"ACA health insurance\"` → law/program topic; omit (unless a **named agency** is the actor)\n- `\"Anti-Weaponization Fund\"` / `\"Full Service Community Schools grant\"` → fund/program topic; omit\n- `\"American Community Survey\"` → publication/survey title; omit (unless **U.S. Census Bureau** or similar agency is the actor)\n- `\"A Mighty Wind\"` / `\"Angelo, My Love\"` → film or performance title; omit\n- `\"Anne Frank House\"` / `\"around the Arc de Triomphe in Paris\"` / `\"in Grant Park\"` → landmark/site/geography; omit\n- `\"American civil society\"` / `\"Arizona families\"` / `\"Arizona grand jury\"` → broad descriptor, not a proper-noun institution; omit\n- `\"Artificial intelligence\"` as a story topic → concept; omit\n- `\"the Chicago area\"` → region; omit\n- `\"Donald Trump\"` / `\"Bernie Sanders\"` / `\"Antonio Martínez Ocasio\"` / `\"Ayo Dosunmu\"` → people; omit\n- `\"Grammy Awards\"` / `\"Super Bowl\"` / `\"World War I\"` → event/history; omit unless the organizing body is named\n\n**Borderline but editorially relevant** — include the row, use the best normal `type`, and set `organization_boundary` to one of:\n- `borderline_brand_platform` — brand/platform/service use may not be organizational (\"sent a message on Twitter\")\n- `borderline_work_title` — column, show, book, film, franchise, publication title, etc. (\"Dear Abby answered a reader\")\n- `borderline_place_business` — business name may be only a location (\"the event happened at Baskin Robbins\")\n- `borderline_event_competition` — use only when an organizing body might exist but context is ambiguous. If the mention is just the event/award/game name (`Grammy Awards`, `Super Bowl`, festival title), **omit** instead of using this boundary.\n\nDo **not** use `other` just because a row is borderline. Omit `organization_boundary` for clear organizations.\n\nExamples:\n- \"Twitter laid off 20 people\" → organization (`company`)\n- \"Joe sent a message on Twitter\" → omit (incidental platform use)\n- \"AMC announced it would close two theaters\" → organization\n- \"Baskin Robbins employees gathered\" → organization (`local_business`)\n- \"The event happened at Baskin Robbins\" → omit unless the business itself matters; if editorially relevant but venue-like, `borderline_place_business`\n\n## Names and types\n\n- Use the most specific conventional proper-noun name.\n- `name` must identify an **institution or group**, not an individual human's given and family name (see **Do not extract**). A label must be a **proper-noun institution**, not a broad descriptor (`American civil society`), fund/program title (`Anti-Weaponization Fund`), publication/survey title (`American Community Survey`), landmark (`Anne Frank House`), or creative-work title (`A Mighty Wind`). When unsure whether a proper noun is a person or an organization, **omit it from organizations** if the text treats them as an individual acting, speaking, or being described.\n- Expand acronyms when known (\"National Basketball Association\" not \"NBA\") unless expansion is ambiguous.\n- **Schools:** use full school names in scorelines, not bare city tokens (\"Brother Rice High School,\" not \"Brother Rice\" alone when naming a school institution). **Never** put a bare scoreline token alone in `name` (not `\"Belvidere\"`, `\"Woodstock\"`, `\"Smith\"`, `\"Park\"`)—expand with your world knowledge to the conventional **full school name** (`Belvidere High School`, `Woodstock High School`, `Smith High School`).\n- **Sports teams:** in athletics coverage, bare school/university names usually mean the **team**, not the campus. Use `sports_team` with pattern `[School] [boys|girls|men's|women's] [sport] team` when sport is inferable from the article. Never emit bare \"Mount Carmel,\" \"Brother Rice,\" or \"Cubs\" alone as `sports_team`. Map nicknames (\"Caravan,\" \"Wolverines\") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor—not players, games, recruiting, or championships.\n- **Prep scorelines (all formats):** when a token appears in a **game result or schedule**—final scores (`St. Louis Park 57 Hopkins 54`, `Belvidere 55, Woodstock 53`, `Brother Rice 48 Marist 41`), scheduled matchups (`Team A at Team B`), or box-score tables—it names a **school team**, not the homonymous city. **Extract both sides.** Expand each token to the full school name plus team when sport is clear (e.g. `Belvidere 55, Woodstock 53` in basketball coverage → `Belvidere High School boys basketball team`, `Woodstock High School boys basketball team`; not `Belvidere` or `Woodstock` alone, and not `school` when the story is about a game). Use dateline, league, sport section, and nearby context to infer state and sport; apply conventional local school names when you know them.\n- **Pro and college teams before player names:** when a team nickname precedes a player, coach, or role descriptor (`Phillies masher Kyle Schwarber`, `Cubs ace`, `Yankees outfielder`), extract the team as `sports_team` using the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`, `New York Yankees`) even if the team is not the grammatical subject of the sentence.\n- One record per organization; merge all `mentions`.\n- `type` slugs: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`\n- **`other` is not a catch-all.** Use a specific `type` when one clearly fits. Use `other` only for a **named institution** that is genuinely organizational but outside the list (e.g. an unusual membership body with a proper name). If the mention is a **law, place, concept, region, or topic**—or you would choose `other` only because nothing fits—**omit it** from `organizations` instead. Never type a law, landmark, or abstract topic as `government` or `other`.\n- `role_in_story`: short plain-language reason it matters\n- `nature`: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`\n- `nature_secondary_tags`: optional 0–2 tags from the same nature vocabulary\n- `mentions`: at least one object with `text` (verbatim snippet) and `quote` (true only for direct quotations) per organization. Prefer a full **sentence or paragraph** containing the organization—not the organization name alone unless the name is the entire sentence.\n\n## Output\n\nReturn **only** valid JSON. No text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
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
