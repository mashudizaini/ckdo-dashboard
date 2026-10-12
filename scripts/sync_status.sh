#!/usr/bin/env bash
# Is everything on the same commit? Laptop, GitHub, DEV, PROD.
# Read-only: fetches and reads, never pulls or changes anything.
# Usage (Git Bash):  bash scripts/sync_status.sh
cd "$(dirname "$0")/.." || exit 1

DEV="user@172.21.2.209:/opt/ckdo/ckdo-dashboard"
PROD="dashboarduser@172.21.2.28:/home/dashboarduser/ckdo/ckdo-dashboard"

git fetch -q origin 2>/dev/null || echo "(gagal fetch GitHub — angka GitHub mungkin basi)"
dirty=$(git status --porcelain --untracked-files=no | wc -l)
printf "%-8s %s%s\n" "LAPTOP" "$(git log -1 --format='%h %s' HEAD | cut -c1-70)" \
  "$([ "$dirty" -gt 0 ] && echo "  [ada $dirty perubahan belum di-commit]")"
printf "%-8s %s\n" "GITHUB" "$(git log -1 --format='%h %s' origin/master | cut -c1-70)"
ahead=$(git rev-list --count origin/master..HEAD); behind=$(git rev-list --count HEAD..origin/master)
[ "$ahead$behind" != "00" ] && echo "         laptop: $ahead commit belum di-push, $behind commit belum di-pull"

for target in "DEV $DEV" "PROD $PROD"; do
  set -- $target
  host=${2%%:*}; dir=${2#*:}
  out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$host" \
        "cd $dir && git log -1 --format='%h %s' | cut -c1-70 && git status --porcelain --untracked-files=no | grep -v 'frontend/package-lock.json' | wc -l" 2>/dev/null)
  if [ -z "$out" ]; then printf "%-8s %s\n" "$1" "(tidak bisa SSH)"; continue; fi
  commit=$(echo "$out" | head -1); n=$(echo "$out" | tail -1)
  printf "%-8s %s%s\n" "$1" "$commit" "$([ "$n" -gt 0 ] && echo "  [ada $n perubahan lokal di server!]")"
done
