# @backfield/ui

Shared React UI primitives for Backfield apps (Agate UI, Stylebook UI, …).

## Tailwind CSS

Components use Tailwind utility classes (`bg-popover`, `border-input`, …). Each app must:

1. Add this package to **Tailwind `content`** so classes are generated, for example:

   ```js
   // tailwind.config.js
   content: [
     "./src/**/*.{ts,tsx}",
     "../../packages/backfield-ui/src/**/*.{ts,tsx}",
   ],
   ```

2. Use the same **CSS variables / theme** as the host app (`--popover`, `--accent`, …), e.g. Agate’s `index.css` pattern.

## `UserAccountMenu`

Icon trigger with dropdown: Change password, optional Manage users (org admin), Log out. Navigation is via callbacks so hosts can use React Router or any router.
