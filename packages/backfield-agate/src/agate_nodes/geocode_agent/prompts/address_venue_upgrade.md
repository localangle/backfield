Return **only** JSON — either `{"upgrade": false}` or `{"upgrade": true, "location":"<one line>"}`.

## Task

The extractor classified this item as **`type`: `address`**. You receive the geocoder’s **`formatted_address`**, the extractor’s **`q`**, optional **`components_json`**, a **baseline** display line already produced for maps/UI, and **story** text (possibly truncated) plus **`geocode_hints`** (or `(none)`).

Sometimes the story **names a specific venue** (theater, arena, campus building, museum, etc.) at that street address. When you are **absolutely certain** of that venue’s proper name from the story, you may **upgrade** the public label to a **named-place** line and downstream code will treat the result as **`place`** instead of **`address`**.

## When `"upgrade": true`

Set `"upgrade": true` **only if all** of the following hold:

1. The story **explicitly** gives a **single** conventional proper name for a venue that **clearly occupies** this address (e.g. same sentence or clause: “… at **North Shore Center for the Performing Arts**, 9501 Skokie Blvd., Skokie …”).
2. You are **absolutely certain** of that name — **no** inference from category alone (“the theater”), **no** chain guess (“the Starbucks”), **no** partial or fuzzy names.
3. **`location`** is a clean publication line: **`{Venue name}, {City}, {ST}`** (US/CA use a **two-letter** postal code for the state). **Omit** the street number from `location` when upgrading.

## When `"upgrade": false`

Use `{"upgrade": false}` whenever:

- The story does not **verbatim-level** support the venue string you would output, or support is ambiguous.
- The site could be a **private residence**, anonymous **suite/office**, **parcel** without a public marquee name, or **multiple** venues could apply.
- You are not **absolutely certain**.

If in doubt, **`upgrade`: false** — a correct address line is better than a wrong venue name.

## Inputs

- **baseline_location**: line already proposed for this geocode (often street + city + state).
- **q**: extractor query / address string.
- **formatted_address**: geocoder line.
- **components_json**: structured fields (may be `{}`).
- **original_text**: story excerpt (may be truncated).
- **geocode_hints**: extractor hints or `(none)`.

Concrete field values follow the `---` separator in the user message.
