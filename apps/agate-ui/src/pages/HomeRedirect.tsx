import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { listProjects } from '@/lib/api'

/**
 * Sends users to the default project (slug `general`, else first by id).
 */
export default function HomeRedirect() {
  const [target, setTarget] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const projects = await listProjects()
        if (cancelled) return
        const def = projects.find((p) => p.slug === 'general') ?? projects[0]
        setTarget(def ? `/project/${encodeURIComponent(def.slug)}` : '/templates')
      } catch {
        if (!cancelled) setTarget('/templates')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (!target) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return <Navigate to={target} replace />
}
