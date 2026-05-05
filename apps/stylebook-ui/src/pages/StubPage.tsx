import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"

export default function StubPage({ title }: { title: string }) {
  const crumbRoot = useScopeBreadcrumbRoot()
  return (
    <div className="container mx-auto p-6">
      <Breadcrumbs
        className="mb-3"
        items={[
          { label: crumbRoot.label, to: crumbRoot.to },
          { label: title },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>This area is not migrated in Backfield yet.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Use Locations in the navigation to work with project-scoped canonical places.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
