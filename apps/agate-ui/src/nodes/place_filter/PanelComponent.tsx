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

import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface PlaceFilterPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function PlaceFilterPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: PlaceFilterPanelProps) {
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null

  const modelOptions =
    nodeMetadata.availableModels && nodeMetadata.availableModels.length > 0
      ? nodeMetadata.availableModels
      : [{ value: 'gpt-5', label: 'GPT-5' }]

  const defaultModel = nodeMetadata.defaultParams?.model || 'gpt-5'

  return (
    <>
      <div className="space-y-4">
        <div>
          <Label className="text-sm font-medium">About</Label>
          <p className="text-sm text-muted-foreground mt-1">{nodeMetadata.description}</p>
          {nodeMetadata.dependencyHelperText ? (
            <p className="text-sm text-muted-foreground mt-2 border-l-2 border-muted pl-3">
              {nodeMetadata.dependencyHelperText}
            </p>
          ) : null}
        </div>

        <div>
          <Label className="text-sm font-medium">Prompt placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Use tokens to pull fields from the merged upstream JSON (same behavior as the original Flowbuilder node):
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — article text
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{locations}'}</code> — extracted locations array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code>,{' '}
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — other paths as supported by the runtime
            </li>
          </ul>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-2 text-sm mt-2">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Model</Label>
            {editMode && setNodes ? (
              <Select
                value={node.data.model || defaultModel}
                onValueChange={(value) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, model: value } } : n
                    )
                  )
                }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded">
                <span className="text-muted-foreground">Model</span>
                <span className="font-medium text-xs">{node.data.model || defaultModel}</span>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Prompt</Label>
            {editMode && setNodes ? (
              <textarea
                value={node.data.prompt ?? nodeMetadata.defaultParams?.prompt ?? ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, prompt: e.target.value } } : n
                    )
                  )
                }}
                placeholder="Leave empty to use the default filter prompt from prompts/filter.md"
                className="w-full min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
              />
            ) : (
              <div className="p-2 bg-muted rounded max-h-48 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {(node.data.prompt ?? nodeMetadata.defaultParams?.prompt) || 'Using default prompt file'}
                </pre>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Output format (JSON example)</Label>
            {editMode && setNodes ? (
              <textarea
                value={node.data.json_format ?? nodeMetadata.defaultParams?.json_format ?? ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, json_format: e.target.value } } : n
                    )
                  )
                }}
                placeholder='[{"index":0,"relevant":true,"reason":""}]'
                className="w-full min-h-[120px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
              />
            ) : (
              <div className="p-2 bg-muted rounded border border-input max-h-48 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono text-muted-foreground">
                  {node.data.json_format ?? nodeMetadata.defaultParams?.json_format ?? ''}
                </pre>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Braces in this block are escaped automatically when appended to the prompt.
            </p>
          </div>
        </div>
      </div>

      {latestData?.locations && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <p className="text-xs text-muted-foreground mt-2">
            Locations kept: {latestData.locations.length}
          </p>
        </div>
      )}
    </>
  )
}
