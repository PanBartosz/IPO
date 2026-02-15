#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1
  pwd
)"

SLUG="delegate-launch"

MANUAL_MD="$ROOT_DIR/docs/delegate-manual/manual.md"
STYLE_CSS_SRC="$ROOT_DIR/docs/delegate-manual/style.css"
LIGHTBOX_JS_SRC="$ROOT_DIR/docs/delegate-manual/lightbox.js"
PANDOC_AFTER_BODY_SRC="$ROOT_DIR/docs/delegate-manual/pandoc-after-body.html"
ASSETS_SRC_DIR="$ROOT_DIR/docs/delegate-manual/assets"

MANUAL_OUT_DIR="$ROOT_DIR/ipo_app/static/manuals/$SLUG"
ASSETS_OUT_DIR="$MANUAL_OUT_DIR/assets"
STYLE_CSS_OUT="$MANUAL_OUT_DIR/style.css"
LIGHTBOX_JS_OUT="$MANUAL_OUT_DIR/lightbox.js"
OUT_HTML="$MANUAL_OUT_DIR/index.html"

mkdir -p "$ASSETS_OUT_DIR"

echo "==> Copying assets"
rsync -a --delete --include="*/" --include="*.png" --exclude="*" "$ASSETS_SRC_DIR/" "$ASSETS_OUT_DIR/"

echo "==> Copying CSS"
cp -f "$STYLE_CSS_SRC" "$STYLE_CSS_OUT"

echo "==> Copying JS"
cp -f "$LIGHTBOX_JS_SRC" "$LIGHTBOX_JS_OUT"

echo "==> Rendering HTML with pandoc"
pandoc "$MANUAL_MD" \
  --from markdown+implicit_figures \
  --to html5 \
  --standalone \
  --toc \
  --toc-depth=3 \
  --css "style.css" \
  --include-after-body "$PANDOC_AFTER_BODY_SRC" \
  --metadata title="IPO Warsaw 2026 — Registration & Surveys Guide" \
  --output "$OUT_HTML"

echo "==> Published"
echo "URL (local): http://localhost:5000/manuals/$SLUG/"
echo "Files: $MANUAL_OUT_DIR"
