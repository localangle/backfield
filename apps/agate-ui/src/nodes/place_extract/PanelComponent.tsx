// Auto-injected metadata for PlaceExtract
const nodeMetadata = {
  "type": "PlaceExtract",
  "name": "PlaceExtract",
  "label": "Place Extract",
  "description": "Extract place information from text using LLM.",
  "category": "extraction",
  "icon": "MapPin",
  "color": "bg-purple-500",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Requires text input or JSON with a \"text\" attribute.",
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
      "id": "locations",
      "label": "Locations",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "gpt-4o-mini",
    "prompt_file": "prompts/extract.md",
    "prompt": "# Location Extraction Service\n\nActing as a state-of-the-art entity extraction service, identify and extract all locations mentioned in the following text. Be maximalist in your approach, but only include things that can be considered physical locations. Any location mentioned in the text, for any reason, should be extracted here.\n\n## Text to Analyze\n\n{text}\n\n## Overview\n\nIn addition to geographic boundaries, streets and roads, regions and neighborhoods, and other common location types, locations you extract should also include the names of businesses, landmarks and other named places.\n\nIf more than one location cited in a paragraph, extract them all.\n\nAs you extract the locations, classify and format them according to the following rules:\n\n## Classification Rules\n\n### Type Classification\n\nClassify each location by the type of geography it represents. Valid types are:\n\n- **place**: A named place. For example: \"Target Headquarters,\" \"Roseville Mall\" or \"White House\". Might contain a city or other geographic boundary information but does not contain an address. Natural places, such as lakes, rivers and mountains should be considered \"natural\" types, not places.\n- **address**: A street address, which must include a house number. This might include block numbers, such as \"500 block of Portland Ave.\" If a place also includes an address, extract only the address and classify it as an \"address.\" Streets or roads without some kind of house number are not addresses.\n- **intersection_road**: An intersection of two non-highway roads, such as Main St. and 2nd St. Even if the story does not describe an intersection in a single string, you may infer it using other information in the article.\n- **intersection_highway**: An intersection where one or both components is an interstate or highway, such as \"I-94 and Selby Ave.\" or \"Hwy. 20 and Hwy. 36\"\n- **street_road**: A single street, road or highway without other geographic information or context, such as an address. For example: \"41st St. N.,\" \"Hennepin Ave.\" or \"I-35\".\n- **span**: A span of road between two points. For example: \"I-35 between Pine City and Hinckley\" or \"Lake Street from Nicollet Avenue S. to 28th Avenue S.\". Note that a span requires both a road and two reference points marking the beginning and end of a span. Just a road, or a road with only one reference point, should use other types as appropriate. \n- **neighborhood**: Explicit mentions of neighborhood names. Do not include the word \"neighborhood\" or any other descriptor in the output. Only the name. So \"North Loop\" not \"North Loop neighborhood\".\n- **region_city**: A description of an area within a city that is not a named place or neighborhood, such as \"South Minneapolis,\" or the \"Chicago lakefront\". It may also refer to named mass-transit lines, such as \"The Green Line\" light rail in Minneapolis. In all of these cases, also extract the city as a separate object. This can also apply to counties, such as \"western Hennepin County, MN\"\n- **city**: The name of a city\n- **county**: The name of a county in a state\n- **region_state**: The name of a region or a general area being described within a state, such as Northern Wisconsin. In these cases, also extract the state as a separate object. Places that reference large cities and their surrounding areas, like \"The Chicago Area\" or \"the East Bay\" are region_states.\n- **state**: A state\n- **region_national**: The name of a region or a general area being described within the United States, such as the South.\n- **country**: A country\n- **natural**: A specific natural feature, such as a river, lake or mountain range. These are generally specific and named features. General descriptions of natural regions, like \"the California coast\" should be considered regions.\n- **other**: Anything that doesn't fit into the categories above\n\n## Formatting Rules\n\n- Return geocodable address strings in all cases where doing so is possible. For example, if a city is mentioned, like \"Minnetonka\" you should return \"Minnetonka, MN\" if it is clear from the story that Minnetonka, MN is the city being referenced. The same logic should be applied to places, addresses, intersections, streets, and other geographies. You may use the context of the story to fill out information that might not specifically be mentioned. States and countries can be presented on their own: \"Minnesota\" and not \"Minnesota, MN\" for example.\n\n- Geocodable address strings for neighborhoods and regions should include their city and state where possible. For example \"Longfellow, Minneapolis, MN\"\n\n- Block numbers should be returned as addresses. For example, \"200 block of Smith St.\" should be returned as \"200 Smith St., Minneapolis, MN\"\n\n- If a range of street numbers is offered in a single string, such as 7603–7619 N. Main St., include only the first number — in this case, 7603 N. Main St.\n\n- Natural places should generally return only the name of the place and the state in which they are attributed, if possible. For example \"Chicago River, IL\"\n\n- Non-geocodable details (e.g., \"eastbound lanes\" or vague references like \"metro\" without a clear definition) should be omitted unless they are necessary for meaningful distinction.\n\n- If a story describes the location of an incident in imprecise terms, such as happening \"near\" a town, but a precise place/landmark, intersection or location is not given, return only the name of the town. For instance \"Highway 61 near Grand Marais\" should just return \"Grand Marais, MN\"\n\n- If a story includes a list of locations, like \"Freeborn, Faribault, Blue Earth, Brown, Waseca, Nicollet, Le Sueur, Rock and Sibley counties all received snow,\" return each item in the list as a separate location (for instance, \"Freeborn County, MN\", \"Faribault County, MN\", etc.)\n\n- Identifiable places and landmarks should be included with as much geographic information as can be inferred from the story. For instance, if a story mentions \"Memorial Hospital,\" and later the context makes it clear that the hospital in question is located in \"Minneapolis,\" return \"Memorial Hospital, Minneapolis, MN\". This also applies to places that are not proper nouns. A reference to something like \"Monticello nuclear power plant\" should be returned as \"Nuclear power plant, Monticello, MN.\"\n\n- Sometimes a story might use a shorthand name to refer to a location on first reference. For example \"Park\" referring to \"St. Louis Park High School\" or \"Minnetonka\" referring to \"Minnetonka High School\". If the context of the story indicates that the shorthand refers to an entity of which you are aware or can be inferred by the text, return the complete name of that entity as a place. Be especially aware of this if the location is a school. For example, return \"Crete-Monee High School\" not just \"Crete-Monee\" if that can be inferred.\n\n- For street_road types, attempt first to return them with a reference city and state if such information can be inferred from the text: for example \"Interstate 55, Springfield, IL\". If a city cannot be inferred, include only a state if possible, such as \"Interstate 35, IA\". If no state can be inferred, perhaps because the story is referencing a road that crosses state boundaries, include only the name of the road: \"Interstate 70\".\n\n- If a street is already listed as part of an intersection or a span, do not include it separately as a street_road.\n\n## Component extraction\n\nYou should also separate each location into components where possible. The types of components you should capture are:\n\n- **full**: The full geocodable string representing the location that you extract. For example, \"Minneapolis, MN\" or \"Longfellow, Minneapolis, MN\"\n- **type**: The type of the location, from the list above.\n- **place**: Only fill this out for named places, such as businesses and landmarks\n  - **name**: The name of the place, for instance \"Dogwood Coffee\" or \"Mississippi River\"\n  - **natural**: Return True if the place represents a natural location that is unlikely to have a street address, such as North Cascades National Park, Island Lake, or the Mississippi River.\n  - **addressable**: Return True if the place is likely to have a findable street address, such as a business, building, school or landmark. Pay special attention to proper nouns, which often indicate addressable locations. Return False in all other cases.\n- **street_road**: Only fill this out for street_road types, where a street or highway is named without a specific address.\n  - **name**: The name of the street\n  - **boundary**: A geocodable string representing the most specific neighborhood, city, county or state boundary that contains the segement of street or road in question, inferred by the context of the article.\n- **span**: Only fill this out for span types, describing a section of road from one place to another. For example, \"Hennepin Ave. from W. 26th St. to W. 28th St.\n  - **start**: The starting point of the span. This is an object containing a \"type\" and \"location\" attribute.\n    - **type**: Either city or intersection. City would be used in cases like \"I-35 from Pine City to Duluth\".\n    - **location**: The intersection or city, formatted as a geocodable string. For example \"Hennepin Ave. and W. 26th St., Minneapolis, MN.\" or \"Pine City, MN\"\n  - **end**: The ending point of the span. Formatted the same as \"start\".\n    - **type**: Either city or intersection.\n    - **location**: The intersection or city, formatted as a geocodable string.\n- **address**: The street address, if applicable. For example \"100 Fake St.\"\n- **neighborhood**: The name of the neighborhood, if applicable. For example \"Upper West Side\"\n- **city**: The name of the city, if applicable. For example \"Milwaukee\"\n- **county**: The name of the county, if applicable. For example \"Boone County\"\n- **state**: The name of the state, if applicable.\n  - **name**: The full name of the state. For example \"California\"\n  - **abbr**: The postal abbreviation for the state. For example \"CA\"\n- **country**: The name of the country, if applicable\n  - **name**: The full name of the country. For example \"United States\"\n  - **abbr**: The ISO 3166-1 country code for the country. For example \"US\"\n\nDo not infer additional information about the locations beyond what is instructed in your formatting rules. The exception of this is country, which you should always include if you can reasonably guess it (most of the time this will be US).\n\nReturn empty objects or strings in cases where a component does not apply to the geography in question.\n\n## Required Fields\n\nReturn the paragraph from which the location was extracted and return it as \"original_text.\" Ensure these are copied verbatim from the story.\n\nReturn a brief description of the nature of the location and its importance in the story under a \"description\" attribute.\n\nThe description should:\n\n1. **Be concise and clear**\n2. **Explain why this geography is relevant** to the overall narrative\n3. **Sound natural and journalistic**\n4. **Be brief** (1-2 sentences maximum)\n\nGenerally, write this as though you are describing the events of the story for residents of the area in question. Do not make reference to the broader story. Only describe the events, localized for the audience of the geography in question.\n\n## Output Format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.\n\nThe results should be returned in a JSON that looks like the following.",
    "json_format": "{\n  \"locations\": [\n    {\n      \"location\": \"100 Fake St., Minneapolis, MN\",\n      \"type\": \"address_intersection\",\n      \"original_text\": \"The car crash occurred on the 100 block of Fake St.\",\n      \"description\": \"A car crash happened at the 100 block of Fake St.\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"100 Fake St.\",\n        \"neighborhood\": \"\",\n        \"city\": \"Minneapolis\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Minnesota\",\n          \"abbr\": \"MN\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Joe's Department Store, Chicago, IL\",\n      \"type\": \"city\",\n      \"original_text\": \"Bob Smith, who visiting at Joe's Department Store in Chicago, said he supported better agriculture policy.\",\n      \"description\": \"Bob Smith, a farmer who supports better agriculture policy, was visiting at Joe's Department Store in Chicago.\",\n      \"components\": {\n        \"place\": {\n          \"name\": \"Joe's Department Store\",\n          \"natural\": false,\n          \"addressable\": true\n        },\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Chicago\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Illinois\",\n          \"abbr\": \"IL\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"8th Ave S., Chicago, IL\",\n      \"type\": \"street_road\",\n      \"original_text\": \"The robberies occurred in several places along 8th Ave S. in Chicago\",\n      \"description\": \"8th Ave S. was the location of several robberies\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {\n          \"name\": \"8th Ave. S.\",\n          \"boundary\": \"Chicago, IL\"\n        },\n        \"span\": {},\n        \"address\": \"8th Ave S.\",\n        \"neighborhood\": \"\",\n        \"city\": \"Chicago\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Illinois\",\n          \"abbr\": \"IL\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Phoenix, AZ\",\n      \"type\": \"city\",\n      \"original_text\": \"It was warmer in Phoenix than in Minneapolis this week.\",\n      \"description\": \"Phoenix was warmer than Minneapolis during the week of July 5.\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Phoenix\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Arizona\",\n          \"abbr\": \"AZ\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Hennepin Ave. between W. 26th St. and W. 28th St.\",\n      \"type\": \"city\",\n      \"original_text\": \"The parade will happen on Hennepin Ave. between W. 26th St. and W. 28th St.\",\n      \"description\": \"A parade is happening along this stretch of Hennepin Ave.\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {\n          \"start\": {\n            \"type\": \"intersection\",\n            \"location\": \"Hennepin Ave. and W. 26th St., Minneapolis, MN\"\n          },\n          \"end\": {\n            \"type\": \"intersection\",\n            \"location\": \"Hennepin Ave. and W. 28th St., Minneapolis, MN\"\n          }\n        },\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Phoenix\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Arizona\",\n          \"abbr\": \"AZ\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    }\n  ]\n}",
    "llmTimeout": 600
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
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface PlaceExtractPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

function formatSamplePlaceTitle(location: {
  location?: unknown
  original_text?: string
}): string {
  const loc = location.location
  if (typeof loc === 'string') {
    return loc
  }
  if (loc && typeof loc === 'object' && 'full' in loc) {
    const full = (loc as { full?: unknown }).full
    if (typeof full === 'string' && full.length > 0) {
      return full
    }
  }
  return typeof location.original_text === 'string' ? location.original_text : ''
}

export default function PlaceExtractPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: PlaceExtractPanelProps) {
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null

  const modelOptions =
    nodeMetadata.availableModels && nodeMetadata.availableModels.length > 0
      ? nodeMetadata.availableModels
      : [{ value: 'gpt-4o-mini', label: 'GPT-4o Mini' }]

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
          <Label className="text-sm font-medium">Input placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Pull fields from upstream JSON into the prompt using these tokens (same behavior as the original
            Flowbuilder Place Extract node):
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — plain text or the <code className="bg-muted px-1 rounded">text</code>{' '}
              field from JSON input
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code> — <code className="bg-muted px-1 rounded">url</code> field
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.images}'}</code> — nested paths (e.g.{' '}
              <code className="bg-muted px-1 rounded">results.images</code>)
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption}'}</code> — one field from each item in an array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code> — multiple fields per array element
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — entire input object as JSON
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
                value={node.data.model || nodeMetadata.defaultParams?.model || 'gpt-4o-mini'}
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
                <span className="font-medium text-xs">
                  {node.data.model || nodeMetadata.defaultParams?.model || 'gpt-4o-mini'}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="pt-2">
          <Label className="text-sm font-medium">Prompt</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.prompt || nodeMetadata.defaultParams?.prompt || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id
                      ? { ...n, data: { ...n.data, prompt: e.target.value } }
                      : n
                  )
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
          <p className="text-xs text-muted-foreground mt-1">
            Tune extraction instructions. Placeholders:{' '}
            <code className="bg-muted px-1 rounded">{'{text}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{url}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.images}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.caption}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{raw}'}</code>.
          </p>
        </div>

        <div className="pt-2">
          <Label className="text-sm font-medium">Output format</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.json_format || nodeMetadata.defaultParams?.json_format || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id
                      ? { ...n, data: { ...n.data, json_format: e.target.value } }
                      : n
                  )
                )
              }}
              placeholder='{ "locations": [] }'
              className="mt-2 min-h-[100px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {node.data?.json_format ||
                  nodeMetadata.defaultParams?.json_format ||
                  '{ "locations": [] }'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Example JSON shape the model should return. Braces are escaped when this is merged into the prompt.
          </p>
        </div>
      </div>

      {latestData && latestData.locations && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>Places found: {latestData.locations.length}</div>
            </div>

            {latestData.locations.length > 0 && (
              <div>
                <Label className="text-xs font-medium">Sample places</Label>
                <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                  {latestData.locations.slice(0, 3).map((location: any, index: number) => (
                    <div key={index} className="text-xs p-2 bg-muted rounded">
                      <div className="font-medium">{formatSamplePlaceTitle(location)}</div>
                      {location.description && (
                        <div className="text-muted-foreground">{location.description}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
