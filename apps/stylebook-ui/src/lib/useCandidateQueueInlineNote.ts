import { useCallback, useState } from "react"

export type UseCandidateQueueInlineNoteOptions = {
  onSave: (candidateId: number, note: string | null) => Promise<void>
}

export function useCandidateQueueInlineNote({ onSave }: UseCandidateQueueInlineNoteOptions) {
  const [noteSavingId, setNoteSavingId] = useState<number | null>(null)
  const [noteEditingId, setNoteEditingId] = useState<number | null>(null)
  const [noteDraftById, setNoteDraftById] = useState<Record<number, string>>({})

  const openInlineNoteEditor = useCallback((candidateId: number, initialText: string) => {
    setNoteEditingId(candidateId)
    setNoteDraftById((prev) => {
      if (prev[candidateId] !== undefined) return prev
      return { ...prev, [candidateId]: initialText }
    })
  }, [])

  const saveInlineNote = useCallback(
    async (candidateId: number) => {
      const raw = noteDraftById[candidateId] ?? ""
      const draft = raw.trim()
      setNoteSavingId(candidateId)
      try {
        await onSave(candidateId, draft ? draft : null)
      } finally {
        setNoteSavingId(null)
      }
    },
    [noteDraftById, onSave],
  )

  return {
    noteSavingId,
    noteEditingId,
    noteDraftById,
    setNoteDraftById,
    setNoteEditingId,
    openInlineNoteEditor,
    saveInlineNote,
  }
}
