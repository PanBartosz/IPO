#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1
  pwd
)"

MANUAL_MD="$ROOT_DIR/docs/delegate-manual/manual.md"
STYLE_CSS="$ROOT_DIR/docs/delegate-manual/style.css"

OUT_DIR="$ROOT_DIR/output/pdf"
TMP_DIR="$ROOT_DIR/tmp/delegate-manual"

OUT_HTML="$TMP_DIR/ipo-delegate-guide.html"
OUT_PDF="$OUT_DIR/ipo-delegate-guide.pdf"

mkdir -p "$OUT_DIR" "$TMP_DIR"

echo "==> Rendering HTML with pandoc"
pandoc "$MANUAL_MD" \
  --from markdown+implicit_figures \
  --to html5 \
  --standalone \
  --embed-resources \
  --resource-path "$ROOT_DIR/docs/delegate-manual" \
  --css "$STYLE_CSS" \
  --metadata title="IPO Warsaw 2026 — Registration & Surveys Guide (Launch)" \
  --output "$OUT_HTML"

echo "==> Rendering PDF with playwright-cli (Chromium)"

# Run playwright-cli via npx without installing project dependencies.
PWCLI=(npx --yes --package @playwright/cli playwright-cli)

# Use a dedicated session so we don't interfere with any existing browser session.
export PLAYWRIGHT_CLI_SESSION=ipo-delegate-guide-pdf

pushd "$TMP_DIR" >/dev/null 2>&1
"${PWCLI[@]}" close >/dev/null 2>&1 || true

# playwright-cli blocks file:// URLs, so serve the HTML via a tiny local HTTP server.
PORT="$(
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
HTTP_PID="$!"
trap 'kill "$HTTP_PID" >/dev/null 2>&1 || true' EXIT

URL="http://127.0.0.1:$PORT/$(basename "$OUT_HTML")"
"${PWCLI[@]}" open "$URL"

PDF_JS=$(cat <<JS
async (page) => {
  await page.waitForLoadState('networkidle');
  await page.pdf({
    path: ${OUT_PDF@Q},
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: '15mm', right: '15mm', bottom: '15mm', left: '15mm' },
  });
}
JS
)

"${PWCLI[@]}" run-code "$PDF_JS"
"${PWCLI[@]}" close >/dev/null 2>&1 || true
popd >/dev/null 2>&1

echo "==> Done"
echo "PDF: $OUT_PDF"
