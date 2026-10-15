#!/usr/bin/env bash
# release.sh - tag-driven release helper.
# Mirrors .github/workflows/release.yml contract: tag must match the
# pyproject/src version single-source-of-truth before tagging.
#
# Usage: ./scripts/release.sh [patch|minor|major]

set -euo pipefail

BUMP="${1:-patch}"

# 1. Read the single source of truth
VERSION=$(python3 -c "import re; m = re.search(r'__version__ = \"(.+?)\"', open('src/__version__.py').read()); print(m.group(1))")
echo "Current version: $VERSION"

# 2. Compute next version
IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
case "$BUMP" in
  major) NEXT="$((MAJOR+1)).0.0" ;;
  minor) NEXT="$MAJOR.$((MINOR+1)).0" ;;
  patch) NEXT="$MAJOR.$MINOR.$((PATCH+1))" ;;
  *) echo "Unknown bump type: $BUMP (use patch|minor|major)"; exit 1 ;;
esac
echo "Next version:    $NEXT"

# 3. Pre-flight gates
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is dirty - commit or stash first."
  exit 1
fi
git fetch origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "ERROR: HEAD is not origin/main - push first."
  exit 1
fi
echo " Gates: clean tree, synced with origin/main ... OK"

# 4. Bump version in BOTH declared locations (source of truth + pyproject)
sed -i "s/__version__ = \"$VERSION\"/__version__ = \"$NEXT\"/" src/__version__.py
sed -i "s/^version = \"$VERSION\"/version = \"$NEXT\"/" pyproject.toml

# 5. Remind about the changelog (the release workflow extracts it)
if ! grep -q "\[$NEXT\]" CHANGELOG.md; then
  echo "WARNING: CHANGELOG.md has no [$NEXT] section yet."
  echo "  Add it now - release notes are extracted from it. (Ctrl-C to abort)"
  read -r -p "Continue anyway? [y/N] " yn
  [[ "$yn" == "y" ]] || { git checkout -- src/__version__.py pyproject.toml; exit 1; }
fi

# 6. Commit the bump, tag, push (tag push triggers release workflow)
git add src/__version__.py pyproject.toml CHANGELOG.md
git commit -m "chore(release): bump version to $NEXT"
git tag -a "v$NEXT" -m "Release v$NEXT"

echo
echo "Next steps:"
echo "  git push origin main --follow-tags   # triggers the release workflow"
echo "  watch: gh run watch"
