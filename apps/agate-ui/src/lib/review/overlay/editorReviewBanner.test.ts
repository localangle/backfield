import { describe, expect, it } from 'vitest'
import type { ProcessedItem } from '@/lib/api'
import { processedItemSectionEditorTouched } from './editorReviewBanner'

function minimalItem(overrides: Partial<ProcessedItem> = {}): ProcessedItem {
  return {
    id: 1,
    run_id: 'run-1',
    synthetic: false,
    input: {},
    status: 'succeeded',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as ProcessedItem
}

describe('processedItemSectionEditorTouched', () => {
  it('detects places overlay edits and stale entries', () => {
    expect(
      processedItemSectionEditorTouched(
        minimalItem({ stale_overlay_entries: [{ anchor: 'gone' }] }),
        'places',
      ),
    ).toBe(true)
    expect(
      processedItemSectionEditorTouched(
        minimalItem({
          overlay: { locations: { by_anchor: { a1: { description: 'Edited' } } } },
        }),
        'places',
      ),
    ).toBe(true)
    expect(processedItemSectionEditorTouched(minimalItem(), 'places')).toBe(false)
  })

  it('detects people and organizations overlay edits', () => {
    expect(
      processedItemSectionEditorTouched(
        minimalItem({ stale_people_overlay_entries: [{ anchor: 'gone' }] }),
        'people',
      ),
    ).toBe(true)
    expect(
      processedItemSectionEditorTouched(
        minimalItem({
          overlay: { organizations: { removed_anchors: ['org1'] } },
        }),
        'organizations',
      ),
    ).toBe(true)
  })

  it('detects story, meta, and custom overlay edits', () => {
    expect(
      processedItemSectionEditorTouched(
        minimalItem({ overlay: { article: { headline: 'Edited headline' } } }),
        'story',
      ),
    ).toBe(true)
    expect(
      processedItemSectionEditorTouched(
        minimalItem({
          article_meta: [
            {
              id: 1,
              meta_type: 'subject',
              category: 'News',
              rationale: 'Added during review.',
              confidence: 1,
              source: 'review',
            },
          ],
        }),
        'meta',
      ),
    ).toBe(true)
    expect(
      processedItemSectionEditorTouched(
        minimalItem({
          overlay: {
            custom_records: {
              quotes: {
                definition: {
                  label: 'Quotes',
                  schema: [{ name: 'speaker', label: 'Speaker', type: 'string' }],
                },
              },
            },
          },
        }),
        'custom',
      ),
    ).toBe(true)
  })
})
