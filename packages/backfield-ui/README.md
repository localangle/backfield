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

## `ShellProductBrand`

Hub-style product title + platform subtitle (`text-3xl` / muted `text-sm`), wrapped in a React Router `Link`. Pass `to`, `productTitle` (e.g. `Agate` or `Stylebook`), and `platformSubtitle` (typically `Backfield Platform`).

## `UserAccountMenu`

Icon trigger with dropdown: shows `userLabel` (typically email) at the top when set, then optional **Change password** (only if `onChangePassword` is passed), optional **Manage users** (org admin + `onManageUsers`), optional **Manage catalogs** (org admin + `onManageCatalogs`), and **Log out**. Navigation is via callbacks so hosts keep their own router.
