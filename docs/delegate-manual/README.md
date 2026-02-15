# Delegate Launch Manual (HTML)

Source of truth: `docs/delegate-manual/manual.md` (Markdown) + `docs/delegate-manual/assets/` (screenshots).

The portal serves published manuals from:

- `ipo_app/static/manuals/<slug>/index.html`
- `ipo_app/static/manuals/<slug>/assets/*`

The manual is available at:

- `/manuals/<slug>/`

## Publish / update

From the repository root:

```bash
./docs/delegate-manual/publish.sh
```

Then restart the app (if needed) and open:

```text
http://localhost:5000/manuals/delegate-launch/
```

## Optional PDF build

If you still need a PDF version for offline use:

```bash
./docs/delegate-manual/build-pdf.sh
```

