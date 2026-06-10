import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ProcessedItem } from '@/lib/api'
import {
  collectProcessedItemImageEmbeddings,
  formatImageEmbeddingModelDetail,
  imageEmbeddingSource,
} from '@/lib/review/content/imageEmbeddingDisplay'

interface ProcessedItemImagesSectionProps {
  item: ProcessedItem
}

export default function ProcessedItemImagesSection({ item }: ProcessedItemImagesSectionProps) {
  const rows = collectProcessedItemImageEmbeddings(item.output ?? item.node_outputs)

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No images with descriptions are available for this story yet.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Images ({rows.length})</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rows.map((row, index) => {
            const src = imageEmbeddingSource(row)
            const description =
              typeof row.generated_text === 'string' ? row.generated_text.trim() : ''
            const caption =
              typeof row.caption === 'string' && row.caption.trim() ? row.caption.trim() : null
            const modelDetail = formatImageEmbeddingModelDetail(row)

            return (
              <Card key={`${src ?? 'image'}-${index}`} className="overflow-hidden">
                <CardContent className="p-0">
                  <div className="flex flex-col md:flex-row">
                    {src ? (
                      <div className="relative w-full md:w-1/2 aspect-video md:aspect-square bg-muted flex-shrink-0">
                        <img
                          src={src}
                          alt={caption || `Image ${index + 1}`}
                          className="w-full h-full object-cover"
                          onError={(event) => {
                            ;(event.target as HTMLImageElement).style.display = 'none'
                          }}
                        />
                      </div>
                    ) : null}
                    <div className="p-4 space-y-3 flex-1">
                      {caption ? (
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">Caption</p>
                          <p className="text-sm mt-1">{caption}</p>
                        </div>
                      ) : null}
                      {description ? (
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">Description</p>
                          <p className="text-sm mt-1 whitespace-pre-wrap break-words">
                            {description}
                          </p>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No description available.</p>
                      )}
                      {modelDetail ? (
                        <p className="text-xs text-muted-foreground pt-2 border-t">{modelDetail}</p>
                      ) : null}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
