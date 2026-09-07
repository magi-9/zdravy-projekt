#!/usr/bin/env bash
# Lokálny commit-msg hook: vynúti Conventional Commits header ešte pred
# commitom, nie až v CI na PR title (.github/workflows/commit-lint.yml).
#
# Prečo aj lokálne: release-please parsuje commit history medzi tagmi a z
# headera (typu) generuje CHANGELOG.md aj verziu. Nekonvenčný commit priamo
# na develop/main (napr. cez merge-commit PR, nie squash) tak znamená
# chýbajúcu/nesprávnu položku v changelogu — CI lintuje len PR title, tento
# hook chráni aj jednotlivé commity.
#
# Typy musia sedieť s .commitlintrc.json (type-enum) a .gitmessage.
set -euo pipefail

msg_file="$1"
header="$(head -n1 "$msg_file")"

# Merge/revert/fixup/squash commity generuje git sám — nevynucujeme na nich
# formát. release-please-generated "chore(main): release X.Y.Z" už sedí na
# bežný pattern nižšie, netreba výnimku.
case "$header" in
  "Merge "*|"Revert "*|"fixup! "*|"squash! "*|"#"*|"")
    exit 0
    ;;
esac

types="feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert|release"
pattern="^(${types})(\([a-z0-9./-]+\))?!?: .+"

fail() {
  echo "❌ $1:"
  echo ""
  echo "    $header"
  echo ""
  echo "Očakávaný tvar:  <type>(<scope>): <subject>"
  echo "Povolené typy:   ${types//|/, }"
  echo ""
  echo "release-please z tohto headera generuje CHANGELOG.md a verziu —"
  echo "pozri .gitmessage pre vzor a príklady."
  exit 1
}

if ! [[ "$header" =~ $pattern ]]; then
  fail "Commit header nesedí na Conventional Commits formát"
fi

# Rovnaké pravidlo ako .commitlintrc.json subject-full-stop.
if [[ "$header" == *. ]]; then
  fail "Subject nesmie končiť bodkou"
fi

# Rovnaké pravidlo ako .commitlintrc.json body-leading-blank — telo bez
# prázdneho riadku po hlavičke release-please/commitlint parsujú nesprávne.
second_line="$(sed -n '2p' "$msg_file")"
if [[ -n "$second_line" ]]; then
  fail "Medzi hlavičkou a telom commitu musí byť prázdny riadok"
fi
