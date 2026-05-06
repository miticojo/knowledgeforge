#!/usr/bin/env bash
# fetch_pdfs.sh - download remote dataset files listed in pdfs.txt
# Idempotent: skips files already present whose sha256 matches the manifest.
# Local file:// rows are skipped (assumed already on disk).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/pdfs.txt"
DEST="${SCRIPT_DIR}/pdfs"
mkdir -p "$DEST"

c_fetch="\033[36m[FETCH]\033[0m"
c_skip="\033[33m[SKIP] \033[0m"
c_ok="\033[32m[OK]   \033[0m"
c_warn="\033[31m[WARN] \033[0m"

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

# skip header line
tail -n +2 "$MANIFEST" | while IFS=$'\t' read -r filename url license sha; do
  [ -z "${filename:-}" ] && continue
  case "$url" in
    file://*) printf "${c_skip} %s (local file://)\n" "$filename"; continue ;;
  esac
  out="${DEST}/${filename}"
  if [ -f "$out" ] && [ "$sha" != "TBD" ] && [ -n "$sha" ]; then
    have="$(sha256_of "$out")"
    if [ "$have" = "$sha" ]; then
      printf "${c_skip} %s (cached, sha matches)\n" "$filename"
      continue
    fi
  fi
  printf "${c_fetch} %s <- %s\n" "$filename" "$url"
  if curl -fL --retry 3 --retry-delay 2 -o "$out" "$url"; then
    have="$(sha256_of "$out")"
    if [ "$sha" = "TBD" ] || [ -z "$sha" ]; then
      printf "${c_ok} %s sha256=%s (manifest=TBD)\n" "$filename" "$have"
    elif [ "$have" = "$sha" ]; then
      printf "${c_ok} %s sha256 verified\n" "$filename"
    else
      printf "${c_warn} %s sha256 mismatch: expected=%s got=%s\n" "$filename" "$sha" "$have"
    fi
  else
    printf "${c_warn} download failed: %s\n" "$url"
  fi
done

echo "Done. Files under: $DEST"
