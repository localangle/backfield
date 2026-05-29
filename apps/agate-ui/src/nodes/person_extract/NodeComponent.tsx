// Auto-injected metadata for PersonExtract
const nodeMetadata = {
  "type": "PersonExtract",
  "name": "PersonExtract",
  "label": "Person Extract",
  "description": "Extract editorially relevant people from text using an LLM.",
  "category": "extraction",
  "icon": "User",
  "color": "bg-indigo-500",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Requires text input or JSON with a \"text\" field.",
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
    "prompt": "# People Extraction Service\n\nActing as a state-of-the-art entity extraction service, identify and extract all editorially relevant people mentioned in the following text.\n\n## Text to Analyze\n\n{text}\n\n## Overview\n\nExtract a person only if:\n1. **Their name is mentioned in the story** (first name, last name, or full name)\n2. They directly matter to the story's events, actions, statements, or reporting, such as:\n   - People whose actions are central to the story\n   - People affected by the events of the story (victims, residents, business owners, witnesses)\n   - People quoted or paraphrased\n   - Officials, employees, or representatives whose statements or actions are relevant\n   - Subjects of investigations, lawsuits, decisions, or policies\n   - Individuals whose identity is necessary for understanding the story\n\n**IMPORTANT**: Do not extract people who are only referred to generically without a name, such as \"a store owner,\" \"the dispatcher,\" \"a teacher,\" \"residents,\" or \"witnesses\" unless a specific name is provided.\n\n## Who Should NOT Be Included\n\nDo not extract:\n\n### Article authors and contributors\n\n- Journalists, reporters, or writers who authored the article\n- Contributors, editors, or other staff who worked on the article\n- Photographers or other media creators credited with the article\n- Byline names or author credits should not be extracted as people in the story\n\n### Non-story-relevant individuals\n\n- Historical figures (e.g., Abraham Lincoln)\n- Religious figures (Jesus, Buddha, Muhammad, saints, prophets)\n- Mythological or fictional characters\n- Celebrities used metaphorically (\"He pulled a Beyoncé move\")\n- People mentioned only as analogies (\"He's no Einstein\")\n- People referenced in idioms or generic cultural shorthand (\"Don't be a Scrooge.\")\n\n### Not involved in the article's events\n\n- Authors of unrelated studies, reports, or research (unless they actively play a role in the story)\n- People mentioned only as optional context or background, not tied to the current events\n- People quoted in other publications unless the article uses them as primary sources for its own reporting\n\n### Institutional misinterpretations\n\n- Do not treat institutions as people, even if personified\n- Example: \"DHS said…\" — do not create a person for this\n- Statements by unnamed institutions (\"the agency said\") do not count as persons\n\n### Generic references without names\n\n- **Do not extract people referred to only by role or title without a name**, such as:\n  - \"a store owner said…\"\n  - \"the dispatcher reported…\"\n  - \"a teacher mentioned…\"\n  - \"the mayor announced…\" (unless the mayor's name is also mentioned)\n  - \"residents said…\"\n  - \"witnesses reported…\"\n  - \"officials stated…\"\n- Only extract if a specific name (first name, last name, or full name) is provided in the article\n- Crowds or groups (\"residents said…\") should never be extracted, even if they are quoted\n\n## Person Identification Rules\n\n### 1. Names Required\n\n**A person must have a name mentioned in the article to be extracted.** This means:\n- First name, last name, or full name must appear in the text\n- Generic titles alone (\"the mayor,\" \"the dispatcher\") are not sufficient\n- If a person is mentioned by both name and title (e.g., \"Mayor John Smith\"), extract them using the name\n\n### 2. Alias & Coreference Handling\n\nYou must merge all references to the same person into one record:\n\n- Full name → last name only later\n- Full name → pronouns referring back\n- Nicknames → official names (if obvious and unambiguous)\n- Role/title references → same person if clearly linked\n\nExample: \"Superintendent Lisa Johnson\" → \"Johnson\" → \"the superintendent\"\n\n### 3. Disambiguation Rules\n\n- If two people share the same last name, maintain separate entries\n- Only merge when there is unambiguous evidence they are the same person\n\n### 4. Pronoun Linking\n\nFor each person, include any sentence or paragraph where a pronoun refers to them, even if their name is not repeated.\n\n## Quote Identification Rules\n\nMark `quote: true` if the mention contains:\n\n- A direct quote attributed to the person (\"I'm not resigning,\" Johnson said.)\n- An indirect quote (Johnson said she would not resign.)\n- A paraphrased attribution (Johnson argued the policy is flawed.)\n\nIf the person is simply mentioned in a quoted segment but not as the speaker, mark `quote: false`.\n\n### Complete quotes when split by attribution\n\nWhen a direct quote is split by attribution (e.g., \"Part one,\" he said. \"Part two.\"), capture the **complete quote** in a single mention—include both the part before and after the attribution. Do not truncate at the attribution.\n\nExample: \"I want to be a source of inspiration for my students,\" he said when asked about the impact on students. \"When you try to be the best musician, player and conductor you can be, that's one way you can inspire them to try to be the best they can be.\"\n\n→ Extract as one mention containing the full text above (both quoted segments plus the attribution between them).\n\n## Mentions List Granularity\n\n- Use sentences as the default unit\n- If sentence boundaries are unclear or broken, use paragraphs instead\n- Each mention should be self-contained and unmodified except for trimming whitespace\n\n## Public Figure Detection\n\nSet `\"public_figure\": true` if the person is widely known, such as:\n\n- Politicians, elected officials\n- CEOs of major organizations\n- Professional athletes\n- Actors, musicians, artists, authors\n- Major business leaders\n- Any person likely to appear in Wikipedia or Ballotpedia\n\nUse common sense and contextual clues.\n\n## Field Requirements\n\n### name\n\nThe complete name as a **flat string** on first mention (e.g. `\"Jane Doe\"`). **Must be an actual name** (first name, last name, or full name). Do not use generic titles like \"the mayor\" or \"a store owner\" — only extract when a name is provided.\n\n### title\n\nThe person's role or position **only**—the job title, role, or descriptor. Include both **official titles** (Mayor, Superintendent, Police Chief, Professor) and **informal or role-based titles** (shortstop, advocate, spokesperson, team captain, store owner, witness).\n\n**CRITICAL**: Do NOT include the organization or affiliation name in the title. Keep title and affiliation separate.\n\n- If the text says \"owner of Billiards on Broadway\" → title: \"Owner\", affiliation: \"Billiards on Broadway\"\n- If the text says \"Former owner of Billiards on Broadway\" → title: \"Former owner\", affiliation: \"Billiards on Broadway\"\n- If the text says \"Superintendent of Chicago Public Schools\" → title: \"Superintendent\", affiliation: \"Chicago Public Schools\"\n\nThe title should be the role/position alone (e.g., \"Owner\", \"Mayor\", \"Spokesperson\"). The affiliation should contain the organization or entity name.\n\n### affiliation\n\nThe institution or organization tied to the title or role. Example: \"Chicago Public Schools,\" \"University of Minnesota,\" \"Billiards on Broadway.\" Do not repeat this in the title field.\n\n### public_figure\n\nSee rules above.\n\n### role_in_story\n\nA concise summary of the person's importance in this article. Should be just a sentence fragment or brief phrase.\n\n### nature\n\nPrimary editorial role of this person **in the story**. Use exactly one of:\n\n`subject`, `source`, `expert`, `official`, `witness`, `affected`, `victim`, `suspect`, `participant`, `observer`, `context`, `other`\n\nExamples: a mayor announcing policy → `official`; someone quoted about the plan → `source` or `affected`; a person arrested → `suspect`; someone who saw an incident → `witness`; the main figure the story is about → `subject`.\n\n### nature_secondary_tags\n\nOptional array of additional values from the same vocabulary when a secondary role clearly applies (often empty).\n\n### type\n\nOptional category when evident (e.g. `politician`, `athlete`, `community member`, `law enforcement`). Omit or use empty string when unclear.\n\n### mentions\n\nEvery instance (sentence or paragraph) where the person appears or is referred to by pronoun. Include:\n\n- Verbatim text\n- Whether it contains a quote from the person (`quote: true`)\n\nDo not combine sentences; each mention is separate.\n\n**CRITICAL**: Each mention MUST be a JSON object with exactly two keys:\n- `\"text\"`: string — the verbatim text of the mention\n- `\"quote\"`: boolean — true if the mention contains a direct/indirect quote from the person\n\n**Never** use plain strings for mentions. Always use objects. Example:\n```json\n\"mentions\": [\n  {{\"text\": \"Johnson said she would not resign.\", \"quote\": true}},\n  {{\"text\": \"The superintendent has been in the role since 2019.\", \"quote\": false}}\n]\n```\n\n## Output Format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.\n\nEach person object **must** include:\n- `name`: string — full name (flat string, not an object)\n- `title`: string — role or position only (official or informal)\n- `affiliation`: string — institution or organization if mentioned\n- `public_figure`: boolean\n- `type`: string — optional person category when evident\n- `role_in_story`: string\n- `nature`: string — one vocabulary value listed above\n- `nature_secondary_tags`: array of strings (same vocabulary; often empty)\n- `mentions`: array of objects, each with `\"text\"` (string) and `\"quote\"` (boolean)\n\nReturn `{ \"people\": [ ... ] }`. When no named people qualify, return `{ \"people\": [] }`.",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_format": "{\n  \"people\": [\n    {\n      \"name\": \"John Smith\",\n      \"title\": \"Mayor\",\n      \"affiliation\": \"City of Chicago\",\n      \"public_figure\": true,\n      \"type\": \"politician\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"official\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Mayor John Smith announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Jane Doe\",\n      \"title\": \"\",\n      \"affiliation\": \"\",\n      \"public_figure\": false,\n      \"type\": \"community member\",\n      \"role_in_story\": \"Local resident supporting the plan\",\n      \"nature\": \"affected\",\n      \"nature_secondary_tags\": [\"source\"],\n      \"mentions\": [\n        {\n          \"text\": \"Jane Doe, a local resident, said she supports the plan.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
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
