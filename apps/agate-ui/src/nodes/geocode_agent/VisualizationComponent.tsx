// Auto-injected metadata for GeocodeAgent
const nodeMetadata = {
  "type": "GeocodeAgent",
  "label": "Geocode Agent",
  "icon": "MapPin",
  "color": "bg-teal-600",
  "description": "Turns PlaceExtract output into map-ready locations: optional Stylebook cache, routing, then external geocoding. Pick routing, geographic reasoning, and evaluation models.",
  "category": "enrichment",
  "requiredUpstreamNodes": [
    "PlaceExtract"
  ],
  "dependencyHelperText": "Requires extracted places as input.",
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
      "id": "places",
      "label": "Places",
      "type": "object"
    },
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "maxLocations": 100,
    "perLocationTimeout": 300,
    "useCache": false,
    "stylebook_id": null,
    "stylebookApiUrl": "",
    "projectSlug": "",
    "evaluationModel": "",
    "geographicReasoningModel": "",
    "routerModel": "",
    "evaluationAiModelConfigId": null,
    "geographicReasoningAiModelConfigId": null,
    "routerAiModelConfigId": null,
    "useCacheLlmAdjudication": true,
    "useCacheLlmAdjudicationOnMissRecall": false
  }
};

/**
 * Geocode geography is reviewed and edited on the processed-item **Review** tab.
 * We intentionally omit a second Leaflet map on the Visualizations tab.
 */
export function buildVisualization(
  _nodeId: string,
  _nodeLabel: string,
  _output: unknown,
): null {
  return null
}
