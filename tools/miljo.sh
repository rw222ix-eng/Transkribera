#!/usr/bin/env bash
# Gör en tom Linuxbehållare redo att köra appen — inget mer.
#
# Läraren kör Windows och Mac; det här skriptet är för de behållare där
# utvecklingen sker (Claude Code på webben). En sådan startar med ett färskt
# klonat repo och ingenting installerat, och första frågan är alltid densamma:
# «starta appen». Utan det här går tio minuter åt till pip innan något syns.
#
# Två saker skiljer listan här från requirements.txt, båda med flit:
#   · pywebview hoppas över — dess beroende proxy_tools bygger inte i
#     behållaren, och fönstret behövs inte: tools/skarp.py kör servern naken.
#   · testberoendena tas med — sviten ska gå att köra direkt.
#
# Idempotent: hittar den allt går den ur på en sekund. Körs av SessionStart-
# kroken i .claude/settings.json, och går att köra för hand.
set -u

cd "$(dirname "$0")/.." || exit 0

# macOS har inget `python`, bara `python3` — och på lärarens maskiner ligger
# beroendena i .venv, inte systemvitt. Behållaren har `python` i PATH som förr.
if [ -x .venv/bin/python ]; then
  python() { .venv/bin/python "$@"; }
elif ! command -v python >/dev/null 2>&1; then
  python() { python3 "$@"; }
fi

if python -c "import fastapi, uvicorn, pydantic, jinja2, httpx, pytest" 2>/dev/null; then
  echo "miljö: klar"
  bash "$(dirname "$0")/hamta_tectonic.sh"
  exit 0
fi

echo "miljö: installerar serverberoenden (pywebview hoppas över) ..."
python -m pip install -q \
  fastapi uvicorn pydantic jinja2 httpx starlette anyio \
  pypdfium2 pillow psutil pytest pytest-cov hypothesis 2>&1 | tail -3

if python -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "miljö: klar — python tools/skarp.py startar appen"
  # PDF-motorn sist: den är tung och får inte hindra att servern går att starta.
  bash "$(dirname "$0")/hamta_tectonic.sh"
else
  echo "miljö: MISSLYCKADES — kör pip för hand"
fi

exit 0
