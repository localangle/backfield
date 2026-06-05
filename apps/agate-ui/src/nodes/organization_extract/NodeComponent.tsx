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
    "prompt": "# Organization Extraction Service\n\nActing as a state-of-the-art entity extraction service, identify and extract all **editorially relevant organizations** mentioned in the text provided at the end of this prompt.\n\n## Overview\n\nExtract an organization only if:\n\n1. **A specific named organization is mentioned** (agency, company, school, team, nonprofit, government body, etc.)\n2. It matters to the story's events, actions, statements, or reporting, such as:\n   - Organizations whose actions or decisions are central to the story\n   - Organizations quoted or paraphrased as sources\n   - Organizations affected by or regulating the events\n   - Employers, institutions, or agencies tied to named people **when the organization itself is editorially relevant** (not only as a person's affiliation shorthand)\n\n**IMPORTANT**: Do not extract generic institutional references without a recognizable name, such as \"the agency,\" \"city officials,\" \"police,\" or \"the school district\" unless the text names the specific organization (e.g. \"Chicago Police Department,\" \"Cook County\").\n\n## Who Should NOT Be Included\n\nDo not extract:\n\n- **Individual people** — extract organizations only, never persons\n- **Unnamed groups** — \"residents,\" \"witnesses,\" \"officials,\" \"employees\" without an organization name\n- **Places that are only geography** — a street, city, or building name is not an organization unless the story treats it as an institution (e.g. \"Wrigley Field\" as a venue operated by a named team or authority)\n- **Article authors and news outlets** when they appear only as bylines or publication credits for this article\n- **Metonyms without a proper name** — \"City Hall said\" without naming the city government body when only the metonym appears\n- **Historical, religious, mythological, or fictional entities** unless they function as real-world organizations in the story's events\n\n## Organization Identification Rules\n\n### 1. Names Required\n\nUse the **most specific conventional name** appearing in the article (e.g. \"Chicago Police Department\" not only \"police\"). You may normalize obvious abbreviations when the full name is clear from context.\n\n### 2. One Record Per Organization\n\nIf the same organization appears multiple times, emit **one** object with **all** supporting `mentions` snippets.\n\n### 3. Type Classification\n\nSet `type` to one of these slugs (use `other` when none fit):\n\n`government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`\n\n### 4. Role and Nature\n\n- **`role_in_story`**: Short phrase describing why this organization matters in the article (plain language, not codes).\n- **`nature`**: Primary editorial role — one of: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`\n- **`nature_secondary_tags`**: Optional list of additional nature values from the same vocabulary (usually 0–2 tags).\n\n### 5. Mentions\n\nEach organization must include a `mentions` array with at least one object:\n\n```json\n{ \"text\": \"<verbatim snippet from the article>\", \"quote\": true|false }\n```\n\nUse `\"quote\": true` only when the snippet is a direct quotation attributed to the organization or its representative.\n\n## Output Format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include explanatory text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "output_format": "{\n  \"organizations\": [\n    {\n      \"name\": \"Chicago City Hall\",\n      \"type\": \"government\",\n      \"role_in_story\": \"Announced a new park initiative\",\n      \"nature\": \"actor\",\n      \"nature_secondary_tags\": [],\n      \"mentions\": [\n        {\n          \"text\": \"Chicago City Hall announced a new park initiative Monday.\",\n          \"quote\": false\n        }\n      ]\n    },\n    {\n      \"name\": \"Chicago Police Department\",\n      \"type\": \"law_enforcement\",\n      \"role_in_story\": \"Will increase patrols near the site\",\n      \"nature\": \"regulator\",\n      \"nature_secondary_tags\": [\"source\"],\n      \"mentions\": [\n        {\n          \"text\": \"The Chicago Police Department said it will increase patrols near the site.\",\n          \"quote\": false\n        }\n      ]\n    }\n  ]\n}\n"
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
