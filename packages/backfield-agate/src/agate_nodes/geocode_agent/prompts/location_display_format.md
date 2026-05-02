Return only `{"location":"<one line>"}` — public **Location** (not the full mailing line in formatted_address).

US-centric (use `type`, `q`, `formatted_address`, `components_json`):

1. Strip trailing `US`/`USA`/`United States` for US domestic. Keep country only if clearly non-US, or `type` is `region_country`, or feature is national/multi-state (then end `, US`, never `USA`).
2. Uppercase only the **first alphabetic character** of the whole string.
3. In-city: `place`,`address`,`neighborhood`,`district`,`intersection_*`,`street_road`,`region_city`,`point`,… → `{Feature}, {City}, {ST}` (US → 2-letter ST).
4. State-level: `city`,`town`,`county`,`region`,`area`,`region_*` except `region_city` → `{Feature}, {State}`; if `type` is `state` → **full state name** only (e.g. Arizona).
5. `natural`: multi-state / park-scale → `{Name}, US`; single-city → `{Name}, {City}, {ST}`.
6. Address/place: if addr leads with a **formal POI/venue** then street → location = venue+city+state only (no street; street stays in formatted_address). Else follow (3) without pasting full addr.

Trim q/addr; do not invent geography. If addr empty, derive conservatively from q+type.
