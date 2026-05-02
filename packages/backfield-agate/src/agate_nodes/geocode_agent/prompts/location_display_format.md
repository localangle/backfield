Return only `{"location":"<one line>"}` — public **Location** (not the full mailing line in formatted_address).

US-centric (use `type`, `q`, `formatted_address`, `components_json`):

1. Strip trailing `US`/`USA`/`United States` for US domestic. Keep country only if clearly non-US, or `type` is `region_country`, or feature is national/multi-state (then end `, US`, never `USA`).
2. **Casing**: **Title-case** place names per comma segment. **Uppercase** any comma segment that is exactly **two letters** and is a valid **US (incl. DC) or Canadian** subdivision code. **Remove consecutive duplicate segments** when two comma-separated parts are the **same** toponym so the line reads **City, ST** not **City, City, ST**. **Lowercase** short joiners (**of, and, the, or, …**) except the **first word** of each segment. Fix **letter + apostrophe + name** tokens (capitalize after `'`; not English contractions). Trailing national `US` stays uppercase.
3. **Order**: Prefer conventional **head toponym before generic placetype** when `q`, `addr`, and `components_json` show they name the **same** incorporated place. Do not invent or merge unrelated segments.
4. In-city: `place`,`address`,`neighborhood`,`district`,`intersection_*`,`street_road`,`region_city`,`point`,… → `{Feature}, {City}, {ST}` (US → 2-letter ST).
5. State-level: `city`,`town`,`county`,`region`,`area`,`region_*` except `region_city` → `{Feature}, {State}`; if `type` is `state` → **full state name** only (no 2-letter code in that slot).
6. `natural`: multi-state / park-scale → `{Name}, US`; single-city → `{Name}, {City}, {ST}`.
7. Address/place: if addr leads with a **formal POI/venue** then street → location = venue+city+state only (no street; street stays in formatted_address). Else follow (4) without pasting full addr.

Trim q/addr; do not invent geography. If addr empty, derive conservatively from q+type.
