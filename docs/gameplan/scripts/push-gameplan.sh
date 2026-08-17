#!/usr/bin/env bash
# Creates the GamePlan branch and pushes this folder to it.
# Run from anywhere. Usage:  ./push-gameplan.sh  [path-to-repo]
set -euo pipefail

REPO_URL="https://github.com/dVerse-Technologies/TASL.git"
BRANCH="GamePlan"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the GamePlan folder
REPO="${1:-$PWD}"

if [ ! -d "$REPO/.git" ]; then
  echo "No git repo at $REPO — cloning into ./TASL"
  git clone "$REPO_URL" TASL
  REPO="$PWD/TASL"
fi

cd "$REPO"
git fetch origin

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git checkout "$BRANCH"
elif git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git checkout -b "$BRANCH" "origin/$BRANCH"
else
  git checkout -b "$BRANCH"
fi

mkdir -p GamePlan
rsync -a --delete "$HERE"/ GamePlan/ 2>/dev/null || cp -R "$HERE"/. GamePlan/

git add GamePlan
if git diff --cached --quiet; then
  echo "Nothing to commit — GamePlan is already up to date."
  exit 0
fi

git commit -m "GamePlan: materials, economy, crew, awards, sizing, machine-readable data"
git push -u origin "$BRANCH"

echo
echo "Pushed to branch '$BRANCH'."
echo "Open a PR: https://github.com/dVerse-Technologies/TASL/compare/$BRANCH?expand=1"
