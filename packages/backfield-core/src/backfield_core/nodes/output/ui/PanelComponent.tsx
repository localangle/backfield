import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface OutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function OutputPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: OutputPanelProps) {
  // Convert array to comma-separated string for display
  const arrayToString = (arr: string[] | undefined): string => {
    if (!arr || arr.length === 0) return ''
    return arr.join(', ')
  }

  // Convert comma-separated string to array
  const stringToArray = (str: string): string[] => {
    if (!str || str.trim() === '') return []
    return str.split(',').map(s => s.trim()).filter(s => s.length > 0)
  }

  const handleExcludeChange = (value: string) => {
    if (!setNodes) return
    // Store both raw string (for editing) and array (for backend)
    // This allows commas to be typed freely
    const excludeArray = stringToArray(value)
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? { 
              ...n, 
              data: { 
                ...n.data, 
                exclude_raw: value, // Keep raw for editing
                exclude: excludeArray.length > 0 ? excludeArray : undefined // Converted array for backend
              } 
            }
          : n
      )
    )
  }

  const handleIncludeChange = (value: string) => {
    if (!setNodes) return
    // Store both raw string (for editing) and array (for backend)
    // This allows commas to be typed freely
    const includeArray = stringToArray(value)
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? { 
              ...n, 
              data: { 
                ...n.data, 
                include_raw: value, // Keep raw for editing
                include: includeArray.length > 0 ? includeArray : undefined // Converted array for backend
              } 
            }
          : n
      )
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            This node consolidates data from all upstream nodes into a single output. It accepts any number of inputs, merges all fields into one object, waits for all upstream nodes to complete, and returns a consolidated data structure.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>
        
        <div className="space-y-3 mt-2">
          <div>
            <Label htmlFor="exclude" className="text-xs text-muted-foreground">
              Exclude Keys (comma-separated)
            </Label>
            {editMode && setNodes ? (
              <Textarea
                id="exclude"
                value={node.data?.exclude_raw ?? arrayToString(node.data?.exclude) ?? ''}
                onChange={(e) => handleExcludeChange(e.target.value)}
                placeholder="locations, node-6, etc."
                className="mt-1 min-h-[60px] text-xs"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">
                  {arrayToString(node.data?.exclude) || 'None'}
                </span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Keys to exclude from the output. Enter keys separated by commas.
            </p>
          </div>

          <div>
            <Label htmlFor="include" className="text-xs text-muted-foreground">
              Include Keys (whitelist, comma-separated)
            </Label>
            {editMode && setNodes ? (
              <Textarea
                id="include"
                value={node.data?.include_raw ?? arrayToString(node.data?.include) ?? ''}
                onChange={(e) => handleIncludeChange(e.target.value)}
                placeholder="places, images, text, etc."
                className="mt-1 min-h-[60px] text-xs"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">
                  {arrayToString(node.data?.include) || 'All keys'}
                </span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              If specified, only these keys will be included in the output (whitelist). Leave empty to include all keys (except excluded ones).
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
