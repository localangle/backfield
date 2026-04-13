import React from 'react'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'

interface GeocodeAgentPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function GeocodeAgentPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: GeocodeAgentPanelProps) {
  const params = node.data || { 
    calculateParents: false,
    useCache: false,
    stylebookApiUrl: '',
    projectSlug: ''
  }
  
  const isDisabled = !(editMode && setNodes)
  
  const handleCalculateParentsChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: { ...n.data, calculateParents: checked } }
            : n
        )
      )
    }
  }

  const handleUseCacheChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: { ...n.data, useCache: checked } }
            : n
        )
      )
    }
  }

  const handleStylebookApiUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: { ...n.data, stylebookApiUrl: e.target.value } }
            : n
        )
      )
    }
  }

  const handleProjectSlugChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: { ...n.data, projectSlug: e.target.value } }
            : n
        )
      )
    }
  }

  // Get latest run data - only show if we have specific node output
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null
  const locationCount = latestData?.locations?.length || 0

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            This node uses LLM reasoning to intelligently geocode locations from PlaceExtract or PlaceFilter. 
            It enhances geocoding accuracy by understanding context and resolving ambiguities.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>
        
        <div className="space-y-3 mt-2">
          <div>
            <Label htmlFor="calculateParents" className="text-xs text-muted-foreground">Calculate Parents</Label>
            {editMode && setNodes ? (
              <div className="mt-1 flex items-center space-x-2">
                <Switch
                  id="calculateParents"
                  checked={params.calculateParents || false}
                  onCheckedChange={handleCalculateParentsChange}
                />
                <Label htmlFor="calculateParents" className="text-xs">
                  {params.calculateParents ? 'Enabled' : 'Disabled'}
                </Label>
              </div>
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs font-mono">{params.calculateParents ? 'Enabled' : 'Disabled'}</span>
              </div>
            )}
          </div>

          <div className="pt-2 border-t">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="useCache"
                checked={params.useCache || false}
                onCheckedChange={handleUseCacheChange}
                disabled={isDisabled}
              />
              <Label htmlFor="useCache" className="text-xs font-medium cursor-pointer">
                Use Cache
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-1 ml-6">
              Match locations to canonical Stylebook locations before using external geocoding
            </p>
          </div>

          {params.useCache && (
            <>
              <div>
                <Label htmlFor="stylebookApiUrl" className="text-xs">Stylebook API URL</Label>
                <Input
                  id="stylebookApiUrl"
                  value={params.stylebookApiUrl || ''}
                  onChange={handleStylebookApiUrlChange}
                  placeholder="http://stylebook-api:8003"
                  className="text-xs"
                  disabled={isDisabled}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Leave empty to use STYLEBOOK_API_URL environment variable
                </p>
              </div>

              <div>
                <Label htmlFor="projectSlug" className="text-xs">Project Slug</Label>
                <Input
                  id="projectSlug"
                  value={params.projectSlug || ''}
                  onChange={handleProjectSlugChange}
                  placeholder="my-project"
                  className="text-xs"
                  disabled={isDisabled}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Required for canonical matching
                </p>
              </div>
            </>
          )}
        </div>
      </div>

      {latestData && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest Run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>Geocoded {locationCount} location{locationCount !== 1 ? 's' : ''}</div>
            </div>
            
            {locationCount > 0 && (
              <div>
                <Label className="text-xs font-medium">Sample Output:</Label>
                <div className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-32 overflow-y-auto">
                  {JSON.stringify(latestData.locations[0], null, 2).substring(0, 200)}
                  {JSON.stringify(latestData.locations[0], null, 2).length > 200 ? '...' : ''}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

