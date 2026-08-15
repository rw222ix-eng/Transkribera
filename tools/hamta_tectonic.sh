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
FIL="tectonic-${VERSION}-x86_64-unknown-linux-musl.tar.gz"
URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${VERSION}/${FIL}"

VARDAR="github.com, objects.githubusercontent.com, relay.fullyjustified.net, data1.fullyjustified.net, archive.org"

if [ -x "$MOTOR/tectonic" ]; then
  echo "tectonic: finns redan i bin/tectonic/"
  exit 0
fi

if [ "$(uname -s)" != "Linux" ]; then
  echo "tectonic: det här skriptet är för Linuxbehållare — på Windows och Mac packas motorn upp för hand"
  exit 0
fi

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
bin="$(find "$tmp" -type f -name tectonic -perm -u+x | head -1)"
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
cd "$ROT" && python -m tools.seed_tectonic_cache \
  || echo "tectonic: seedningen gick inte igenom — motorn finns, men första provet hämtar sina paket över nätet"

exit 0
