// Auto-injected metadata for PlaceFilter
const nodeMetadata = {
  "type": "PlaceFilter",
  "name": "PlaceFilter",
  "label": "Place Filter",
  "category": "filter",
  "icon": "Filter",
  "color": "bg-orange-500",
  "description": "Filter PlaceExtract locations based on LLM relevance judgments.",
  "requiredUpstreamNodes": [
    "PlaceExtract"
  ],
  "dependencyHelperText": "Requires extracted places (text + locations) from Place Extract.",
  "inputs": [
    {
      "id": "locations",
      "label": "Locations",
      "type": "array",
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
      "id": "locations",
      "label": "Locations",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "gpt-5",
    "prompt_file": "prompts/filter.md",
    "output_format_file": "prompts/_filter_output.md",
    "prompt": "# Location Filtering Service\n\nYou will be given the text of a news article along with a JSON object containing locations that have been extracted from it. Your job is to classify whether the location is relevant based on the following criteria.\n\n## Text to Analyze:\n{text}\n\n## Locations to Filter:\n{locations}\n\n## Relevant Locations\n\nRelevant locations are literal, physical locations that are relevant to the events of the story. Examples include: places where key news events took place, where sources or characters are from, places described for detail or scene-setting, places mentioned for context and datelines at the beginnings of stories that indicate a reporter travelled there.\n\nOther cases where locations should be marked as relevant include:\n\n- **Areas represented by lawmakers** should also always be considered relevant. For instance, in the case of Joe Smith, R-Maple Grove, the location \"Maple Grove, MN\" is always relevant.\n- **Places that are affected by policy issues, decisions or the events** described within a story, particularly if it is a place that residents of a town or neighborhood might commonly visit, such as a performing arts venue, park, sports venue, etc.\n- **Places that provide biographical context** about people in a story, such as where they live, work, grew up or went to school.\n\n## Irrelevant Locations\n\nIrrelevant locations are locations that are mentioned in the story but are not relevant to the events or context of the story itself. Categories of irrelevant locations include, but are not limited to:\n\n- **Metonyms**: For example, \"Washington\" when it is used as a reference to the U.S. government, \"City Hall\" when it is used as a reference to city government, or a city name like \"Chicago\" when it is used as a stand-in for a professional or college sports team, like the Chicago Bears.\n- **Synecdoche**: Places that represent a larger entity or a subset (e.g., \"Hollywood\" for the U.S. film industry, \"Silicon Valley\" for the tech industry).\n- **Metaphor**: Places used to draw comparisons or symbolic meanings (e.g., \"Fort Knox\" to represent something highly secure or valuable).\n- **Idiomatic expressions**: Common phrases or idioms where the place isn't meant literally (e.g., \"Main Street\" symbolizing everyday people or small businesses).\n- **Historical or cultural references**: Places mentioned in a way that invokes historical or cultural connotations rather than their current geographical reality (e.g., \"Rome wasn't built in a day\").\n- **Colloquialisms and slang**: Locations used in informal expressions or slang that have non-literal meanings (e.g., \"The Big Apple\" for New York City in a cultural sense rather than just the geographic city).\n- **Allegory or symbolism**: Places used to convey a broader theme or idea, like \"Eden\" representing paradise, not a literal location.\n- **Hyperbole**: Exaggerated references to places for emphasis (e.g., \"a trip to Timbuktu\" to indicate somewhere very remote, not the actual city in Mali).\n- **Clichés**: Overused phrases involving places that don't carry their literal meaning (e.g., \"all roads lead to Rome\" as a cliché for many paths leading to the same result).\n- **Generic locations**: References to unnamed and generic places that could possibly refer to more than one location, such as \"Bank, Minneapolis, MN\" or \"Gas station, Wadena, MN\"\n- **Duplicate locations**: Each location should only appear in the output once.\n- **Countries and continents**: Mentions of countries or continents, including the U.S. or North America, are generally irrelevant. They are too broad to be useful.\n- **Ambiguous chains**: If it is likely that the place has multiple locations, but the story does not contain enough information to identify a specific location, mark it as irrelevant. For example \"Target, Minneapolis, MN\"\n\n## Institutions\n\nThe names of businesses, organizations and institutions are a special case. They may be relevant or irrelevant depending on their context.\n\nGenerally, if an institution is mentioned without direct geographic context, it should be considered irrelevant. For example, \"The ACLU protested the ruling\" or \"Joe Smith, the president of the ACLU\" refers to the ACLU as an institution, not a physical location. These should be marked irrelevant. \"The protest took place at ACLU headquarters\" references a specific place and therefore would be relevant.\n\nCity, county and state agencies, such as the Minnesota Department of Education or St. Paul Public Works, should generally not be marked as relevant unless key news events are noted to have taken place at their headquarters, buildings or properties. The same is true of membership organizations like unions and professional associations.\n\nThe locations of small businesses that are referenced are typically relevant. The headquarters of large companies are generally not, unless an event took place there. For example, in a case like \"Target Corp. objected to the policy,\" Target should be listed as irrelevant. In a case like \"employees gathered at Target headquarters,\" it should be considered relevant.\n\nAn exception to all of this is high school sports and other contests. High schools and locations that are mentioned in reference to sports or other contests should always be considered relevant.\n\n## Duplicate Locations\n\nLocations that are duplicative should be marked irrelevant. In the case of locations that are mentioned multiple times, mark the most detailed instance as relevant and less detailed instances as irrelevant.\n\nIn the case of region types, keep both the region and any state, city, county or other geography it refers to or includes. For example \"Northern Arizona\" should keep both \"Northern Arizona\" and \"Arizona\". The same is true with cities, like \"South Los Angeles\" and \"Los Angeles\".\n\nIf a street is already listed as part of an intersection or a span, its constituent streets_road objects should be marked as irrelevant. \n\n## Ambiguous Locations\n\nLocations that refer to generic or ambiguous places, such as \"store, Minneapolis, MN\" or \"rooftop, St. Cloud, MN\" should be marked as irrelevant — especially if the city, state and other more specific geographic information described therein are accounted for by another object. City, state and national regions, such as \"Southwest Missouri\" or \"the Pacific Northwest\" should be considered relevant. \n",
    "json_format": "[{\"index\":0,\"relevant\":true,\"reason\":\"\"}]",
    "llmTimeout": 600,
    "output_format": "## Output Format\n\nReturn a JSON array of judgments with format: `[{{\"index\": 0, \"relevant\": true, \"reason\": \"...\"}}, ...]`\n\nEach judgment should have:\n   - `index`: integer index of the location in the input array\n   - `relevant`: boolean indicating if the location should be kept\n   - `reason`: string explaining the decision (optional)\n\nHere is an example:\n\n```json\n[\n  {{\n    \"index\": 0,\n    \"relevant\": true,\n    \"reason\": \"This location is directly relevant to the main topic\"\n  }},\n  {{\n    \"index\": 1,\n    \"relevant\": false,\n    \"reason\": \"This location is mentioned but not central to the story\"\n  }}\n]\n```\n\nReturn only the JSON array, no additional text or explanation.\n"
  },
  "availableModels": [
    {
      "value": "gpt-5.2",
      "label": "GPT 5.2"
    },
    {
      "value": "gpt-5.1",
      "label": "GPT 5.1"
    },
    {
      "value": "gpt-5",
      "label": "GPT-5"
    },
    {
      "value": "gpt-5-mini",
      "label": "GPT-5 Mini"
    },
    {
      "value": "gpt-5-nano",
      "label": "GPT-5 Nano"
    },
    {
      "value": "gpt-4o",
      "label": "GPT-4o"
    },
    {
      "value": "gpt-4o-mini",
      "label": "GPT-4o Mini"
    },
    {
      "value": "gpt-4-turbo",
      "label": "GPT-4 Turbo"
    },
    {
      "value": "claude-haiku-4-5-20251001",
      "label": "Claude 4.5 Haiku"
    },
    {
      "value": "claude-sonnet-4-5-20250929",
      "label": "Claude 4.5 Sonnet"
    },
    {
      "value": "claude-opus-4-1-20250805",
      "label": "Claude 4.1 Opus"
    }
  ]
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

interface PlaceFilterData {
  model?: string
}

function PlaceFilterNode({ data, selected }: NodeProps<PlaceFilterData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('PlaceFilter', 'h-4 w-4')
  const bgColor = getNodeBgColor('PlaceFilter')
  const title = nodeMetadata?.label || 'Place Filter'

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="locations"
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
          {dependencyHelperText && (
            <p className="text-xs text-muted-foreground mt-1">{dependencyHelperText}</p>
          )}
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="locations"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(PlaceFilterNode)
