export function defaultSelectedSavedPlaceIds(
  items: Array<{ id: number; suggested_for_geometry?: boolean }>,
): number[] {
  return items.filter((item) => item.suggested_for_geometry === true).map((item) => item.id)
}
