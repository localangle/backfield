import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export type StylebookPermissions = { can_edit: boolean }

export async function fetchStylebookPermissions(
  stylebookSlug: string,
): Promise<StylebookPermissions> {
  return stylebookJsonFetch<StylebookPermissions>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/permissions`,
  )
}

