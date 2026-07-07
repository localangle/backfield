// Auto-injected metadata for PersonExtract
const nodeMetadata = {
  "type": "PersonExtract",
  "name": "PersonExtract",
  "label": "Person Extract",
  "description": "Extract editorially relevant people from text.",
  "category": "extraction",
  "icon": "User",
  "color": "bg-indigo-500",
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
      "id": "people",
      "label": "People",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "prompt_file": "prompts/extract.md",
    "prompt": "# People Extraction Service\n\nExtract every editorially relevant **person** named in the news text at the end of this prompt. Return only valid JSON.\n\nA person is relevant when they are named in the story (first name, last name, or full name) and matter to its events: actors, victims, witnesses, sources quoted or paraphrased, officials, subjects of investigations or policies.\n\n## Hard stops — the person test\n\nApply this test to **every row before you emit it**: *is `name` the name of an individual human being?* If not — or if you are unsure — **omit the row**. A missing row is always better than a person record for an organization, place, role label, or product. This is the most common and most damaging extraction error.\n\nNever emit as `people.name`:\n\n| Category | Examples | Where it belongs |\n|----------|----------|------------------|\n| Role or role + agency, no personal name | `ICE agent`, `Illinois Border Patrol agent`, `Chicago police officer`, `federal authorities`, `store owner`, `the mayor` | Omit entirely |\n| Government body, agency, or acronym | `ATF`, `DHS`, `FBI`, `Alcohol, Tobacco, Firearms and Explosives`, `National Transportation Safety Board`, `Illinois Gaming Board`, `Cook County State's Attorney's Office` | Organization extract |\n| Legislature or governing body | `Illinois General Assembly`, `General Assembly`, `City Council`, `County Board` | Organization extract |\n| Company, firm, or fund | `H&R Block`, `Engaged Capital`, `Permanent Capital`, `BlackEdge Capital`, `Kittelson & Associates`, `Finkl Steel`, `American Ancestors` | Organization extract |\n| School or campus | `Loyola Academy`, `Glenbard East High School`, `University of Chicago` | Organization extract |\n| Media outlet or call sign | `ESPN 1000`, `WBEZ`, `CBS2`, `BBC` | Organization extract |\n| Sports team or league | `Chicago Sky`, `Team USA`, `MLB` | Organization extract |\n| Law or statute | `Presidential Records Act of 1978`, `Clean Air Act`, `First Amendment` | Omit |\n| Software or AI product | `Gemini AI`, `ChatGPT` | Omit |\n| Consumer brand alone | `Budweiser`, `Google`, `Coca-Cola` | Omit |\n| City, place, airport, or venue | `Buenos Aires`, `Anchorage`, `O'Hare Airport`, `Wrigley Field` | Place extract |\n| Family or collective | `the Sackler family`, `the couple`, `residents`, `witnesses` | Omit (extract named individual members separately) |\n\n**Warning signs that a name is an institution, not a person:** it contains **Office, Department, Bureau, Agency, Administration, Authority, Commission, Board, Division, Corporation, Company, Foundation, Institute, Association, Union, School, Academy, University, Hospital, Medical Center, Capital, Partners, Holdings, Ventures, Equity, Associates, LLC, Inc., Media, News**; it is an all-caps acronym (`CTA`, `DHS`, `PBS`); or it ends in a number (`ESPN 1000`). Investment firms and funds ending in **Capital**, **Partners**, or **Holdings** are companies — never people.\n\nInstitutions stay institutions even when personified as the grammatical subject: `\"DHS said…\"`, `\"WBEZ reported…\"`, `\"the American Medical Association announced…\"` never create a person. Extract the named **individual** when one appears (`\"Detective Maria Lopez of the Chicago Police Department\"` → person `Maria Lopez`), never the organization itself.\n\n**One exception — bands are people:** named musical groups and recording acts (`Pearl Jam`, `The Beatles`, `Alice Cooper` as the act) go in `people` with `type`: `artist_entertainer` and `public_figure`: `true` when widely known. Do not put bands in organization extraction.\n\nIf a borderline row must be emitted anyway, set `review_handling`: `auto_defer`, `review_reason_code`: `not_a_person`.\n\n## Also do not extract\n\n- **Article authors and staff**: bylines, contributors, editors, photographers credited on the article.\n- **Non-story figures**: historical figures (Abraham Lincoln), religious or fictional characters, celebrities used metaphorically or in analogies (\"He's no Einstein\").\n- **Background-only people**: authors of unrelated studies, people quoted only in other publications, optional context not tied to the story's events.\n\n## Identity rules\n\n1. **A name is required.** Generic titles alone (\"the mayor,\" \"a detective\") never create a person. Title-only references may merge into an existing named person's record but cannot create one.\n2. **Merge coreferences** into one record: full name → last name → pronouns → nicknames → role references, when clearly the same person (\"Superintendent Lisa Johnson\" → \"Johnson\" → \"the superintendent\").\n3. **Surnames from family references**: when the article names a relative of someone with an established surname (`Rocky Wirtz's brother, Peter` → `Peter Wirtz`), use the full inferred name, set `surname_inferred_from_relative`: `true`, and route with `review_handling`: `flag_review`, `review_reason_code`: `first_name_only`. Do not infer from vague references when the anchor surname is not established in the same passage.\n4. **Namesakes stay separate.** Two people sharing a last name get separate entries; merge only with unambiguous evidence.\n5. **Pronoun mentions count.** Include sentences where a pronoun refers to the person even when the name is not repeated.\n\n## Fields\n\n### name\n\nThe fullest personal name form used in the article, as a flat string (`\"Jane Doe\"`). Strip honorifics and post-nominals (`Gov.`, `Dr.`, `Mr.`, `Rev.`, `Sen.`, `Jr.`, `Ph.D.`, …): `\"Gov. J.B. Pritzker\"` → `\"JB Pritzker\"` with `title`: `Governor`. Write initials **without periods** (`\"PT Barnum\"`, `\"JB Pritzker\"`). If the article uses only a surname after introduction, use the fullest form established earlier.\n\n### title\n\nThe role or position **only** — official (Mayor, Police Chief) or informal (shortstop, spokesperson, store owner). Never include the organization name: \"owner of Billiards on Broadway\" → `title`: `Owner`, `affiliation`: `Billiards on Broadway`.\n\n### affiliation\n\nThe organization tied to the title, written AP-style with the fullest clear name (`ACLU` → `American Civil Liberties Union`; `Sox` → `Boston Red Sox`). Empty string when none is stated or implied.\n\n**Sports teams (critical):** assign a team only when the text clearly ties it to the person — `\"Cubs ace Shota Imanaga\"`, `\"Kyle Tucker of the Cubs\"`, `\"former Yankees slugger Aaron Judge\"`. Never assign a team from game context alone: in `\"The Cubs beat the Pirates 5-3. Kyle Tucker homered.\"`, do not give Tucker either team unless his team was established elsewhere. When unsure, leave `affiliation` empty — a wrong team (especially the opponent) causes serious catalog errors.\n\n### public_figure\n\n`true` when widely known: politicians, major executives, professional athletes, entertainers, anyone likely to appear in Wikipedia or Ballotpedia.\n\n### role_in_story\n\nBrief phrase summarizing why this person is in the article.\n\n### nature\n\nPrimary editorial role in the story, exactly one of:\n\n`subject`, `source`, `expert`, `official`, `witness`, `affected`, `victim`, `suspect`, `participant`, `observer`, `context`, `other`\n\nMayor announcing policy → `official`; someone quoted about it → `source` or `affected`; person arrested → `suspect`; main figure of the story → `subject`.\n\n### nature_secondary_tags\n\nOptional array from the same vocabulary when a secondary role clearly applies (often empty).\n\n### type\n\nStory-relative role — one slug (classify why they appear in **this story**, not full biography):\n\n`athlete`, `coach`, `sports_official`, `sports_executive`, `elected_official`, `government_official`, `political_staff`, `lawyer_legal_advocate`, `judge_court_official`, `law_enforcement_public_safety`, `crime_justice_subject`, `business_owner_executive`, `business_professional`, `labor_union_representative`, `artist_entertainer`, `media_journalism`, `arts_culture_professional`, `education_research_expert`, `healthcare_worker`, `community_member`, `unknown`, `other`\n\nPrefer story function over job title: chef at a restaurant opening → `business_owner_executive`; chef profiled for creative work → `arts_culture_professional`; chef quoted as a neighbor → `community_member`. Mayor on policy → `elected_official`; agency director → `government_official`; police chief → `law_enforcement_public_safety`; person charged → `crime_justice_subject`; judge → `judge_court_official`; resident quoted → `community_member`. Use `unknown` when the role cannot be inferred; `other` only when the role is clear but no category fits.\n\n### sort_key\n\nLowercase last name (`\"doe\"` for Jane Doe), or the sole name token for mononyms.\n\n### mentions\n\nEvery sentence (or paragraph when sentence boundaries are broken) where the person appears or is referenced by pronoun, verbatim except trimmed whitespace. Each mention is a separate object — never combine sentences, never use plain strings:\n\n```json\n\"mentions\": [\n  {{\"text\": \"Johnson said she would not resign.\", \"quote\": true}},\n  {{\"text\": \"The superintendent has been in the role since 2019.\", \"quote\": false}}\n]\n```\n\nMark `quote: true` when the mention contains a direct quote, indirect quote, or paraphrased attribution **from that person**; `false` when they are merely mentioned inside someone else's quote. When a direct quote is split by attribution (\"Part one,\" he said. \"Part two.\"), capture the complete quote as one mention including the attribution between the parts.\n\n## Review routing (canonical linking)\n\n| Situation | `review_handling` | `review_reason_code` |\n|-----------|-------------------|----------------------|\n| Child (minor) | `auto_defer` | `child` |\n| Animal (named pet, etc.) | `auto_defer` | `animal` |\n| Non-person that had to be emitted (organization, place, role label, product) | `auto_defer` | `not_a_person` |\n| Stage name or alias without a clear legal name (`Prince`) | `flag_review` | `stage_name_or_alias` |\n| Descriptive pseudonym or anonymous-source label (`TRUTH-TELLER IN ARKANSAS`) | `flag_review` | `pseudonym` |\n| First name only, no surname anywhere in the article | `flag_review` | `first_name_only` |\n| Surname inferred from a family reference | `flag_review` | `first_name_only` (note which relative established it) |\n| Normal named person with full identity | `none` | omit |\n\nInclude a short editor-facing `review_message` whenever handling is not `none`. Use `auto_defer` only for children, animals, and non-people; aliases, pseudonyms, and first-name-only mentions use `flag_review` so editors see them in the open queue.\n\n## Output format\n\nReturn ONLY valid JSON — no explanatory text. Each person object must include:\n\n- `name`: string — full personal name (flat string)\n- `title`: string — role or position only\n- `affiliation`: string — organization, or empty string\n- `public_figure`: boolean\n- `type`: string — one taxonomy slug from **type** (never invent categories)\n- `sort_key`: string — lowercase last name\n- `role_in_story`: string\n- `nature`: string — one vocabulary value from **nature**\n- `nature_secondary_tags`: array of strings (same vocabulary; often empty)\n- `mentions`: array of objects with `\"text\"` (string) and `\"quote\"` (boolean)\n- `review_handling`: string — `none`, `flag_review`, or `auto_defer`\n- `review_reason_code`: string — when handling is not `none`: `child`, `animal`, `not_a_person`, `stage_name_or_alias`, `pseudonym`, or `first_name_only`\n- `review_message`: string — short explanation when handling is not `none`\n- `surname_inferred_from_relative`: boolean — `true` only for inferred family surnames\n\nReturn `{{ \"people\": [ ... ] }}`. When no named people qualify, return `{{ \"people\": [] }}`.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_mode": "compact",
    "output_format": "{\n  \"people\": [\n    {\n      \"name\": \"John Smith\",\n      \"title\": \"Mayor\",\n      \"affiliation\": \"City of Chicago\",\n      \"public_figure\": true,\n      \"type\": \"elected_official\",\n      \"sort_key\": \"smith\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"official\",\n      \"nature_secondary_tags\": [],\n      \"review_handling\": \"none\",\n      \"mentions\": [\n        {\n          \"text\": \"Mayor John Smith announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Buddy\",\n      \"title\": \"\",\n      \"affiliation\": \"\",\n      \"public_figure\": false,\n      \"type\": \"\",\n      \"sort_key\": \"buddy\",\n      \"role_in_story\": \"Family dog mentioned in the story\",\n      \"nature\": \"other\",\n      \"nature_secondary_tags\": [],\n      \"review_handling\": \"auto_defer\",\n      \"review_reason_code\": \"animal\",\n      \"review_message\": \"Identified as an animal\",\n      \"mentions\": [\n        {\n          \"text\": \"The family dog Buddy was unharmed.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Kyle Schwarber\",\n      \"title\": \"\",\n      \"affiliation\": \"Philadelphia Phillies\",\n      \"public_figure\": true,\n      \"type\": \"athlete\",\n      \"sort_key\": \"schwarber\",\n      \"role_in_story\": \"Among major-league home run leaders\",\n      \"nature\": \"context\",\n      \"nature_secondary_tags\": [],\n      \"review_handling\": \"none\",\n      \"mentions\": [\n        {\n          \"text\": \"His 20 home runs trailed only Phillies masher Kyle Schwarber's 22 in the majors, and his 44 walks ranked fifth.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Prince\",\n      \"title\": \"\",\n      \"affiliation\": \"\",\n      \"public_figure\": true,\n      \"type\": \"artist_entertainer\",\n      \"sort_key\": \"prince\",\n      \"role_in_story\": \"Referenced by stage name only\",\n      \"nature\": \"subject\",\n      \"nature_secondary_tags\": [],\n      \"review_handling\": \"flag_review\",\n      \"review_reason_code\": \"stage_name_or_alias\",\n      \"review_message\": \"Stage name or alias — confirm full identity before linking\",\n      \"mentions\": [\n        {\n          \"text\": \"Prince performed at the venue last year.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

interface PersonExtractData {
  model?: string
}

function PersonExtractNode({ data, selected }: NodeProps<PersonExtractData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('PersonExtract', 'h-4 w-4')
  const bgColor = getNodeBgColor('PersonExtract')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Person Extract
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
          id="people"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(PersonExtractNode)
