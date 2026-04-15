import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Trash2, Plus, Key, AlertCircle, Edit } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { listProjectApiKeys, setProjectApiKey, deleteProjectApiKey, updateProject, type ApiKey, type ApiKeyCreate, type Project } from '@/lib/api'
import ProjectAccessKeysPanel, {
  type ProjectAccessKeysPanelHandle,
} from '@/components/ProjectAccessKeysPanel'
import { format } from 'date-fns'

export type ProjectSettingsHandle = {
  openSystemPromptEdit?: () => void
  openAccessKeyCreate?: () => void
  openAddProviderSecret?: () => void
}

interface ProjectSettingsProps {
  project: Project | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Full-width panel for project detail page (no dialog chrome). */
  variant?: 'dialog' | 'inline'
  /** With `variant="inline"`, render only this block (project detail tabs). */
  inlineScope?: 'system' | 'credentials'
  /** Called after project metadata changes (name, slug, system prompt). */
  onRemoteUpdated?: () => void
  /** When true with `variant="inline"`, primary actions render in the project page toolbar. */
  primaryActionsInToolbar?: boolean
}

const AVAILABLE_KEY_TYPES = [
  { value: 'OPENAI_API_KEY', label: 'OpenAI API Key', description: 'For GPT models and embeddings' },
  { value: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key', description: 'For Claude models' },
  { value: 'GEOCODIO_API_KEY', label: 'Geocodio API Key', description: 'For geocoding services' },
  { value: 'PELIAS_API_KEY', label: 'Pelias API Key', description: 'For geocoding services' },
  { value: 'BRAVE_SEARCH_API_KEY', label: 'Brave Search API Key', description: 'For web search and place information' },
  { value: 'AWS_ACCESS_KEY_ID', label: 'AWS Access Key ID', description: 'For S3 bucket access' },
  { value: 'AWS_SECRET_ACCESS_KEY', label: 'AWS Secret Access Key', description: 'For S3 bucket access' },
  { value: 'AWS_SESSION_TOKEN', label: 'AWS Session Token', description: 'For temporary S3 credentials (optional)' },
  { value: 'MAPBOX_API_TOKEN', label: 'Mapbox API Token', description: 'Required for map visualizations on processed items' },
]

const KNOWN_PROVIDER_KEYS = new Set(AVAILABLE_KEY_TYPES.map((t) => t.value))

const ProjectSettings = forwardRef<ProjectSettingsHandle, ProjectSettingsProps>(function ProjectSettings(
  {
    project,
    open,
    onOpenChange,
    variant = 'dialog',
    inlineScope,
    onRemoteUpdated,
    primaryActionsInToolbar = false,
  },
  ref,
) {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Form state for adding new API key
  const [newKeyType, setNewKeyType] = useState('')
  const [newKeyValue, setNewKeyValue] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  
  // Form state for editing existing API key
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editKeyValue, setEditKeyValue] = useState('')
  
  // Form state for project name editing
  const [projectName, setProjectName] = useState('')
  const [editingProjectName, setEditingProjectName] = useState(false)
  
  // Form state for system prompt editing
  const [systemPrompt, setSystemPrompt] = useState('')
  const [editingSystemPrompt, setEditingSystemPrompt] = useState(false)

  const accessKeysPanelRef = useRef<ProjectAccessKeysPanelHandle>(null)

  useImperativeHandle(ref, () => {
    if (variant === 'inline' && inlineScope === 'system') {
      return {
        openSystemPromptEdit: () => setEditingSystemPrompt(true),
      }
    }
    if (variant === 'inline' && inlineScope === 'credentials') {
      return {
        openAccessKeyCreate: () => accessKeysPanelRef.current?.openCreateDialog(),
        openAddProviderSecret: () => setShowAddForm(true),
      }
    }
    return {}
  })

  useEffect(() => {
    if (variant !== 'inline' && !open) {
      setApiKeys([])
      setLoading(false)
      setSaving(false)
      setError(null)
      setNewKeyType('')
      setNewKeyValue('')
      setShowAddForm(false)
      setEditingKey(null)
      setEditKeyValue('')
      setProjectName('')
      setEditingProjectName(false)
      setSystemPrompt('')
      setEditingSystemPrompt(false)
      return
    }
    if (!project) return
    setProjectName(project.name)
    setSystemPrompt(project.system_prompt || '')
    if (variant === 'inline' && inlineScope === 'system') {
      return
    }
    loadApiKeys()
  }, [open, project, variant, inlineScope])

  const loadApiKeys = async () => {
    if (!project) return
    
    try {
      setLoading(true)
      setError(null)
      const keys = await listProjectApiKeys(project.id)
      setApiKeys(keys)
    } catch (err) {
      setError('Failed to load API keys')
      console.error('Failed to load API keys:', err)
    } finally {
      setLoading(false)
    }
  }


  const handleAddKey = async () => {
    if (!project || !newKeyType || !newKeyValue.trim()) return
    
    try {
      setSaving(true)
      setError(null)
      
      const newKey: ApiKeyCreate = {
        key_name: newKeyType,
        value: newKeyValue.trim()
      }
      
      await setProjectApiKey(project.id, newKey)
      
      // Reset form and reload keys
      setNewKeyType('')
      setNewKeyValue('')
      setShowAddForm(false)
      await loadApiKeys()
    } catch (err) {
      setError('Failed to save API key')
      console.error('Failed to save API key:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteKey = async (keyName: string) => {
    if (!project) return
    
    try {
      setSaving(true)
      setError(null)
      
      await deleteProjectApiKey(project.id, keyName)
      await loadApiKeys()
    } catch (err) {
      setError('Failed to delete API key')
      console.error('Failed to delete API key:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleEditKey = (keyName: string) => {
    setEditingKey(keyName)
    setEditKeyValue('') // Clear the value for security
  }

  const handleSaveEdit = async () => {
    if (!project || !editingKey || !editKeyValue.trim()) return
    
    try {
      setSaving(true)
      setError(null)
      
      const updateData: ApiKeyCreate = {
        key_name: editingKey,
        value: editKeyValue.trim()
      }
      
      await setProjectApiKey(project.id, updateData)
      
      // Reset form and reload keys
      setEditingKey(null)
      setEditKeyValue('')
      await loadApiKeys()
    } catch (err) {
      setError('Failed to update API key')
      console.error('Failed to update API key:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setEditingKey(null)
    setEditKeyValue('')
  }

  const handleSaveProjectName = async () => {
    if (!project || !projectName.trim()) return
    
    try {
      setSaving(true)
      setError(null)
      
      await updateProject(project.id, { name: projectName.trim() })
      setEditingProjectName(false)
      onRemoteUpdated?.()
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    } catch (err) {
      setError('Failed to update project name')
      console.error('Failed to update project name:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleCancelProjectNameEdit = () => {
    setProjectName(project?.name || '')
    setEditingProjectName(false)
  }

  const handleSaveSystemPrompt = async () => {
    if (!project) return
 
    try {
      setSaving(true)
      setError(null)
 
      await updateProject(project.id, { system_prompt: systemPrompt.trim() || null })
      setEditingSystemPrompt(false)
      onRemoteUpdated?.()
    } catch (err) {
      setError('Failed to update system prompt')
      console.error('Failed to update system prompt:', err)
    } finally {
      setSaving(false)
    }
  }
 
  const handleCancelSystemPromptEdit = () => {
    setSystemPrompt(project?.system_prompt || '')
    setEditingSystemPrompt(false)
  }

  const getKeyTypeInfo = (keyName: string) => {
    return AVAILABLE_KEY_TYPES.find(type => type.value === keyName)
  }

  const providerKeys = apiKeys.filter((k) => KNOWN_PROVIDER_KEYS.has(k.key_name))

  const getAvailableKeyTypes = () => {
    const existingKeyNames = providerKeys.map((key) => key.key_name)
    return AVAILABLE_KEY_TYPES.filter((type) => !existingKeyNames.includes(type.value))
  }

  if (!project) return null

  const errorAlert =
    error && (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )

  const projectNameSection =
    variant !== 'inline' && (
      <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">Project Name</h3>
                {!editingProjectName && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEditingProjectName(true)}
                  >
                    <Edit className="h-4 w-4 mr-2" />
                    Edit
                  </Button>
                )}
              </div>

              {editingProjectName ? (
                <Card>
                  <CardContent className="p-4">
                    <div className="space-y-4">
                      <div>
                        <Label htmlFor="project-name">Project Name</Label>
                        <Input
                          id="project-name"
                          value={projectName}
                          onChange={(e) => setProjectName(e.target.value)}
                          placeholder="Enter project name..."
                          className="mt-1"
                        />
                      </div>

                      <div className="flex gap-2">
                        <Button
                          onClick={handleSaveProjectName}
                          disabled={!projectName.trim() || saving}
                          size="sm"
                        >
                          {saving ? 'Saving...' : 'Save Changes'}
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleCancelProjectNameEdit}
                          size="sm"
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-medium">{projectName}</h4>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
      </div>
    )

  const systemPromptSection = (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">System Prompt</h3>
              {!editingSystemPrompt &&
                !(variant === 'inline' && inlineScope === 'system' && primaryActionsInToolbar) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEditingSystemPrompt(true)}
                >
                  <Edit className="h-4 w-4 mr-2" />
                  Edit
                </Button>
              )}
            </div>

            {editingSystemPrompt ? (
              <Card>
                <CardContent className="p-4">
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="system-prompt">System Prompt</Label>
                      <textarea
                        id="system-prompt"
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                        placeholder="Enter system prompt for all LLM calls in this project..."
                        className="mt-1 w-full min-h-[120px] p-3 border border-input bg-background rounded-md text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        rows={6}
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        This prompt will be used as the system message for all LLM calls in this project.
                      </p>
                    </div>

                    <div className="flex gap-2">
                      <Button
                        onClick={handleSaveSystemPrompt}
                        disabled={saving}
                        size="sm"
                      >
                        {saving ? 'Saving...' : 'Save Changes'}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleCancelSystemPromptEdit}
                        size="sm"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      {systemPrompt ? (
                        <div>
                          <h4 className="font-medium mb-2">Current System Prompt</h4>
                          <div className="bg-muted p-3 rounded-md text-sm whitespace-pre-wrap">
                            {systemPrompt}
                          </div>
                        </div>
                      ) : (
                        <div>
                          <h4 className="font-medium text-muted-foreground">No system prompt set</h4>
                          <p className="text-sm text-muted-foreground">
                            Add a system prompt to customize how LLMs behave in this project
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
  )

  const credentialsSection = (showCredentialsHeading: boolean) => (
    <div className="w-full min-w-0">
      {showCredentialsHeading && (
        <h3 className="text-lg font-semibold mb-4">Credentials</h3>
      )}
      {project ? (
        <ProjectAccessKeysPanel
          ref={accessKeysPanelRef}
          projectId={project.id}
          primaryActionsInToolbar={primaryActionsInToolbar}
        />
      ) : null}
      <h4 className="text-base font-semibold mb-1">Integration secrets</h4>
      <p className="text-sm text-muted-foreground mb-4">
        Keys for OpenAI, Mapbox, AWS, and other providers used by flows in this project (stored
        encrypted on the server).
      </p>
      {loading ? (
        <div className="text-center py-4">
          <div className="text-sm text-muted-foreground">Loading...</div>
        </div>
      ) : (
        <div className="space-y-4 w-full min-w-0">
          {!primaryActionsInToolbar ? (
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAddForm(true)}
                disabled={saving}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add provider secret
              </Button>
            </div>
          ) : null}
          {providerKeys.length === 0 ? (
            <Card>
              <CardContent className="text-center py-8">
                <Key className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h4 className="font-medium mb-2">No provider secrets</h4>
                <p className="text-sm text-muted-foreground mb-4">
                  Add secrets for OpenAI, Mapbox, AWS, and other integrated providers.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {providerKeys.map((apiKey) => {
                const keyInfo = getKeyTypeInfo(apiKey.key_name)
                return (
                  <Card key={apiKey.key_name}>
                    <CardContent className="p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <h4 className="font-medium">{keyInfo?.label || apiKey.key_name}</h4>
                            <Badge variant="secondary" className="text-xs">
                              {apiKey.key_name}
                            </Badge>
                          </div>
                          {keyInfo?.description && (
                            <p className="text-sm text-muted-foreground mb-2">{keyInfo.description}</p>
                          )}
                          <p className="text-xs text-muted-foreground">
                            Added {format(new Date(apiKey.created_at), 'MMM d, yyyy')}
                          </p>
                        </div>
                        <div className="flex gap-1 shrink-0">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEditKey(apiKey.key_name)}
                            disabled={saving}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteKey(apiKey.key_name)}
                            disabled={saving}
                            className="text-destructive hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}

          {editingKey && KNOWN_PROVIDER_KEYS.has(editingKey) && (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="text-base">Edit API key</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="edit-key-name">Key type</Label>
                  <Input id="edit-key-name" value={editingKey} disabled className="bg-muted" />
                </div>

                <div>
                  <Label htmlFor="edit-key-value">API key value</Label>
                  <Input
                    id="edit-key-value"
                    type="password"
                    value={editKeyValue}
                    onChange={(e) => setEditKeyValue(e.target.value)}
                    placeholder="Enter new API key value..."
                    className="font-mono text-sm"
                  />
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleSaveEdit}
                    disabled={!editKeyValue.trim() || saving}
                    size="sm"
                  >
                    {saving ? 'Saving...' : 'Save changes'}
                  </Button>
                  <Button variant="outline" onClick={handleCancelEdit} size="sm">
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {showAddForm && (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="text-base">Add provider secret</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="key-type">Key type</Label>
                  <Select value={newKeyType} onValueChange={setNewKeyType}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select API key type" />
                    </SelectTrigger>
                    <SelectContent className="min-w-[20rem]">
                      {getAvailableKeyTypes().map((type) => (
                        <SelectItem key={type.value} value={type.value} title={type.description}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="key-value">API key value</Label>
                  <Input
                    id="key-value"
                    type="password"
                    value={newKeyValue}
                    onChange={(e) => setNewKeyValue(e.target.value)}
                    placeholder="Enter your API key..."
                    className="font-mono text-sm"
                  />
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleAddKey}
                    disabled={!newKeyType || !newKeyValue.trim() || saving}
                    size="sm"
                  >
                    {saving ? 'Saving...' : 'Save key'}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowAddForm(false)
                      setNewKeyType('')
                      setNewKeyValue('')
                    }}
                    size="sm"
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )

  const inlineShell = (children: ReactNode) => (
    <div className="space-y-6 w-full min-w-0">{children}</div>
  )

  if (variant === 'inline' && inlineScope === 'system') {
    return inlineShell(
      <>
        {errorAlert}
        {systemPromptSection}
      </>
    )
  }

  if (variant === 'inline' && inlineScope === 'credentials') {
    return inlineShell(
      <>
        {errorAlert}
        {credentialsSection(false)}
      </>
    )
  }

  const settingsBody = (
    <div className="space-y-6 w-full min-w-0">
      {errorAlert}
      {projectNameSection}
      {systemPromptSection}
      {credentialsSection(true)}
    </div>
  )

  if (variant === 'inline') {
    return settingsBody
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(100vw-2rem,48rem)] max-w-none max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            Project Settings - {project.name}
          </DialogTitle>
          <DialogDescription>
            Manage project settings, API access keys, and provider integration secrets.
          </DialogDescription>
        </DialogHeader>

        {settingsBody}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
})

export default ProjectSettings
