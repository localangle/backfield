# GeoJSON import dev fixtures

Use these files for manual testing during development.

- `import-mapping-sample.geojson`: includes a valid row, a missing-name row, and a missing-geometry row to exercise mapping + required-field gating.

## Manual verification (Issue 4)

1. Open `/import/locations?project=<slug>`.
2. Upload `import-mapping-sample.geojson`.
3. Click **Analyze**, then **Continue to mapping**.
4. Pick mappings and proceed to **Review**.
5. Edit label/type/address for at least two rows.
6. Exclude at least one row.
7. Confirm the “Computed import payload (debug)” JSON reflects edits and exclusions.

