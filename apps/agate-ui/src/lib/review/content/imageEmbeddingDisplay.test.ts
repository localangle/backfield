import { describe, expect, it } from 'vitest'

import {
  collectProcessedItemImageEmbeddings,
  formatImageEmbeddingModelDetail,
} from './imageEmbeddingDisplay'

describe('imageEmbeddingDisplay', () => {
  it('collects image embedding rows from nested output', () => {
    const rows = collectProcessedItemImageEmbeddings({
      stylebook_output: {
        image_embeddings: [
          {
            url: 'https://example.com/a.jpg',
            generated_text: 'A red barn.',
            embedding_model: 'text-embedding-3-small',
            embedding_dimensions: 1536,
            description_model: 'gpt-4o-mini',
          },
        ],
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0]?.generated_text).toBe('A red barn.')
  })

  it('formats model detail for review cards', () => {
    expect(
      formatImageEmbeddingModelDetail({
        vision_model: 'gpt-4o-mini',
        embedding_model: 'text-embedding-3-small',
        embedding_dimensions: 1536,
      }),
    ).toBe('gpt-4o-mini · text-embedding-3-small · 1536 dimensions')
  })
})
