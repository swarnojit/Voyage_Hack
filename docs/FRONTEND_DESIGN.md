# TripParadox Studio frontend

## External template foundation

Design system reference: [Tabler](https://github.com/tabler/tabler), an MIT-licensed Bootstrap-based dashboard kit.
The solution uses its **admin-layout conventions** (sidebar / page wrapper / card / table / badges / form controls) while creating original TripParadox markup, application logic, CSS, and all illustrations. It does not clone a copyrighted booking website or reuse a proprietary company's assets.

The repo is immediately usable **offline**, because our original CSS provides the full styling. The optional, authentic upstream CSS can be integrated without a CDN:

```bash
npm install
npm run vendor:tabler
```

That copies pinned `@tabler/core@1.4.0/dist/css/tabler.min.css` to `backend/app/static/vendor/tabler-core.css`. The HTML loads that file first and the TripParadox brand stylesheet second. The upstream licence text is copied alongside when available. **Do not claim the official Tabler CSS is prebundled** in the default ZIP; it is installed only when these commands are run.

## What changed

- White operations workspace with deep navy sidebar, cobalt-blue interaction colour, restrained KPI cards, original workflow illustration and new sign-in screen.
- Actual mobile nav drawer and dark/light appearance switch.
- Scanner displays its planned five-stage flow, AI model information, SQL-backed execution timeline and reproducible proofs.
- Rebuilt travel sandbox uses an OTA-inspired search result layout, original local SVG skyline assets, functional destination/hotel filtering, hotel holds and the same SQL booking ledger.
- Other pages (findings, API inventory, security, audit) use consistent cards, panels, tables and status components.
- JWT remains in memory; dynamic HTML data goes through the existing escaping helper; CSP remains same-origin only.

## Visual inspection

The screenshots in `docs/` are Chromium captures of the actual static UI code using seeded **illustrative** state because the container's browser policy blocked navigating to local HTTP servers. The backend API and SQL flows are separately covered by automated Python tests. These are not screenshots of a real TBO environment.

## Editing points

- `backend/app/static/index.html`: login, navigation, page shell
- `backend/app/static/styles.css`: design tokens, responsive CSS, UI components
- `backend/app/static/app.js`: views, buttons, fetch calls, render functions
- `backend/app/static/art/`: locally generated skyline SVG assets
- `backend/app/static/vendor/tabler-core.css`: optional locally vendored Tabler CSS

## License and safety

The Tabler framework is MIT licensed; see https://github.com/tabler/tabler/blob/dev/LICENSE. Original TripParadox code is under the included project MIT licence. Do not use externally hosted copies of commercial travel websites, real customer datasets, or real supplier credentials in this simulator. The scanner remains limited to the local synthetic application.
