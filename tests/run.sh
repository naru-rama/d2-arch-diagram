#!/bin/bash
set -euo pipefail
[ $# -le 1 ] || { echo "usage: tests/run.sh [--update]" >&2; exit 1; }

skill=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/aws-diagram-test.XXXXXX")
trap 'rm -rf "$work"' EXIT
status=0

for src in "$skill"/examples/*.d2; do
  name=$(basename "$src" .d2)
  cp "$src" "$work/"
  if ! "$skill/bin/aws-diagram" render "$work/$name.d2" >"$work/$name.log" 2>&1; then
    echo "NG $name: 描画に失敗した"
    cat "$work/$name.log"
    status=1
    continue
  fi
  first=$(shasum -a 256 "$work/$name.svg" | cut -d' ' -f1)
  "$skill/bin/aws-diagram" render "$work/$name.d2" >/dev/null 2>&1
  second=$(shasum -a 256 "$work/$name.svg" | cut -d' ' -f1)
  expected="$skill/tests/expected/$name.sha256"
  if [ "$first" != "$second" ]; then
    echo "NG $name: 同じ入力から 2 回描いた SVG が違う"
    status=1
  elif [ "${1:-}" = "--update" ]; then
    mkdir -p "$(dirname "$expected")"
    echo "$first" >"$expected"
    echo "更新 $name"
  elif [ "$(cat "$expected" 2>/dev/null)" != "$first" ]; then
    echo "NG $name: 期待する SVG と違う（意図した変更なら --update で更新する）"
    status=1
  else
    echo "OK $name"
  fi
  sed 's/^/   /' "$work/$name.log"
done
exit $status
