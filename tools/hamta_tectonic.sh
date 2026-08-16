#!/usr/bin/env bash
# Hämtar PDF-motorn till en Linuxbehållare, så att den bygger PDF likadant som
# lärarens Windows- och Mac-maskiner gör.
#
# bin/tectonic/ är gitignorerad — binären är tiotals megabyte och paketcachen
# mer, och repot delar kod, inte data. På lärarens maskiner packas motorn upp en
# gång och ligger kvar. En behållare börjar tom varje gång, och utan det här
# skriptet slutar varje prov och arbetsblad som en .tex utan PDF.
#
# TVÅ nedladdningar krävs, och de går till olika ställen:
#   1. binären — GitHubs släpp (github.com → objects.githubusercontent.com)
#   2. TeX-paketen — Tectonics egen bundle (relay/data1.fullyjustified.net,
#      som i sin tur ligger på archive.org)
#
# Skälet till att skriptet misslyckas VÄNLIGT är mätt, inte gissat. I behållaren
# där det skrevs (Claude Code på webben, 2026-08-15) går de två nedladdningarna
# olika:
#   · binären HÄMTAS UTAN PROBLEM. Nätpolicyn släpper fram GitHubs
#     nedladdningsväg (/releases/download/... svarar 200) men nekar sidorna runt
#     den (/releases/latest och api.github.com svarar 403). Därför är versionen
#     SPIKAD här: skriptet KAN inte fråga vilken som är senast, och ska inte
#     låtsas att det kan.
#   · paketen NEKAS. relay.fullyjustified.net svarar «unsuccessful tunnel».
#     Utan dem finns motorn men har inga typsnitt och paket att sätta med.
# Öppnas de värdarna i miljöns nätpolicy blir det här skriptet hela vägen.
# Tills dess går det ur med 0 och säger vad som saknas — en tom behållare ska
# inte bli oanvändbar för att PDF-motorn inte gick att hämta.
#
#     bash tools/hamta_tectonic.sh
set -u

ROT="$(cd "$(dirname "$0")/.." && pwd)"
MOTOR="$ROT/bin/tectonic"
VERSION="0.15.0"

VARDAR="github.com, objects.githubusercontent.com, relay.fullyjustified.net, data1.fullyjustified.net, archive.org"

if [ -x "$MOTOR/tectonic" ]; then
  echo "tectonic: finns redan i bin/tectonic/"
  exit 0
fi

# Målet står inte i skriptet utan i maskinen. Skriptet var Linux-bara och sa åt
# Mac att packa upp för hand — men bin/tectonic/ är gitignorerad, så VARJE ny
# maskin står inför samma moment, och det ska vara ett kommando överallt.
# Windows har ingen bash här; där gäller fortfarande uppackning för hand.
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)         MAL="x86_64-unknown-linux-musl" ;;
  Linux/aarch64|Linux/arm64) MAL="aarch64-unknown-linux-musl" ;;
  Darwin/arm64)         MAL="aarch64-apple-darwin" ;;      # Apple Silicon
  Darwin/x86_64)        MAL="x86_64-apple-darwin" ;;       # Intel-Mac
  *)
    echo "tectonic: ingen färdig binär för $(uname -s)/$(uname -m) — packa upp motorn i bin/tectonic/ för hand"
    exit 0 ;;
esac

FIL="tectonic-${VERSION}-${MAL}.tar.gz"
URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${VERSION}/${FIL}"

mkdir -p "$MOTOR"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "tectonic: hämtar $FIL ..."
if ! curl -fsSL --max-time 300 -o "$tmp/t.tar.gz" "$URL"; then
  echo "tectonic: NEDLADDNINGEN NEKADES eller misslyckades."
  echo "tectonic: miljöns nätpolicy måste släppa fram: $VARDAR"
  echo "tectonic: utan motorn sparas prov och arbetsblad som .tex — appen säger det själv i kvittot."
  exit 0
fi

tar -xzf "$tmp/t.tar.gz" -C "$tmp" || { echo "tectonic: arkivet gick inte att packa upp"; exit 0; }
# Bara namnet, inget -perm: BSD:s find (Mac) och GNU:s tolkar rättighetsuttryck
# olika, och körflaggan sätts ändå av chmod nedan.
bin="$(find "$tmp" -type f -name tectonic | head -1)"
[ -n "$bin" ] || { echo "tectonic: hittade ingen binär i arkivet"; exit 0; }
cp "$bin" "$MOTOR/tectonic"
chmod +x "$MOTOR/tectonic"
echo "tectonic: $("$MOTOR/tectonic" --version 2>&1 | head -1)"

# Paketcachen. Utan den hämtar Tectonic varje TeX-paket vid första körningen —
# första provet blir minutlångt, och i en behållare utan nät blir det inget
# prov alls. Seedningen kompilerar ett representativt dokument genom appens
# egna mallar och skriver .seeded när det gick igenom; exam_pdf.py läser den
# markören och kör --only-cached först då.
echo "tectonic: seedar paketcachen (kan ta några minuter) ..."
# `python` finns inte på en Mac med Homebrew-python — bara `python3`.
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "tectonic: ingen python hittad — seedningen hoppas över"; exit 0; }
cd "$ROT" && "$PY" -m tools.seed_tectonic_cache \
  || echo "tectonic: seedningen gick inte igenom — motorn finns, men första provet hämtar sina paket över nätet"

exit 0
