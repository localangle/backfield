/** Agate API — project list for the Stylebook header picker (session cookie). */

const agateBase = (): string => import.meta.env.VITE_AGATE_API_BASE ?? "/api/agate"

export interface Project {
  id: number
  slug: string
  name: string
}

export async function fetchProjects(): Promise<Project[]> {
  const response = await fetch(`${agateBase()}/projects`, { credentials: "include" })
  if (!response.ok) {
    throw new Error(`Failed to fetch projects: ${response.statusText}`)
  }
  return response.json() as Promise<Project[]>
}
