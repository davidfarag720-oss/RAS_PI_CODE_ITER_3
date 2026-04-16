#!/usr/bin/env bash
# deploy.sh — Build frontend, create release tarball, publish to GitHub Releases
# Usage: ./deploy/deploy.sh [major|minor|patch|X.Y.Z]
# Default: patch bump
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GITHUB_REPO="davidfarag720-oss/RAS_PI_CODE_ITER_3"

# gh CLI may not be in PATH on Windows — find it
GH="gh"
if ! command -v gh &>/dev/null; then
    if [ -x "/c/Program Files/GitHub CLI/gh.exe" ]; then
        GH="/c/Program Files/GitHub CLI/gh.exe"
    else
        echo "ERROR: gh CLI not found. Install from https://cli.github.com/" >&2
        exit 1
    fi
fi
VERSION_FILE="$REPO_ROOT/VERSION"

# ── 1. Determine new version ──────────────────────────────────────────────────
CURRENT=$(cat "$VERSION_FILE" | tr -d '[:space:]')
BUMP="${1:-patch}"

bump_version() {
    local version="$1" part="$2"
    IFS='.' read -r major minor patch <<< "$version"
    case "$part" in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "${major}.$((minor + 1)).0" ;;
        patch) echo "${major}.${minor}.$((patch + 1))" ;;
        *)     echo "$part" ;;  # treat as literal version
    esac
}

NEW_VERSION=$(bump_version "$CURRENT" "$BUMP")
echo "Version: $CURRENT → $NEW_VERSION"

# ── 2. Build frontend ─────────────────────────────────────────────────────────
echo ""
echo "Building frontend..."
cd "$REPO_ROOT/frontend"
npm ci --silent
npm run build
echo "  Frontend built → frontend/dist/"
cd "$REPO_ROOT"

# ── 3. Bump VERSION and commit ────────────────────────────────────────────────
echo "$NEW_VERSION" > "$VERSION_FILE"
git add "$VERSION_FILE"
git commit -m "chore: bump version to v$NEW_VERSION"

# ── 4. Create tarball ─────────────────────────────────────────────────────────
TARBALL_NAME="ficio-v${NEW_VERSION}.tar.gz"
TARBALL_PATH="/tmp/$TARBALL_NAME"

echo ""
echo "Creating release tarball..."
tar czf "$TARBALL_PATH" \
    --exclude='.git' \
    --exclude='frontend/node_modules' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.planning' \
    --exclude='.claude' \
    --exclude='.pytest_cache' \
    --exclude='mockups' \
    --exclude='nul' \
    --exclude='*.egg-info' \
    -C "$(dirname "$REPO_ROOT")" \
    "$(basename "$REPO_ROOT")"

# Rename root directory inside tarball to match install name
# (re-pack with correct strip path)
TARBALL_FINAL="/tmp/ficio-release-$$"
mkdir -p "$TARBALL_FINAL"
tar xzf "$TARBALL_PATH" -C "$TARBALL_FINAL"
INNER_DIR=$(ls "$TARBALL_FINAL")
mv "$TARBALL_FINAL/$INNER_DIR" "$TARBALL_FINAL/ficio-v${NEW_VERSION}"
tar czf "$TARBALL_PATH" -C "$TARBALL_FINAL" "ficio-v${NEW_VERSION}"
rm -rf "$TARBALL_FINAL"

echo "  Tarball: $TARBALL_PATH"

# ── 5. Tag and push ───────────────────────────────────────────────────────────
echo ""
echo "Tagging and pushing..."
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
git push origin main
git push origin "v${NEW_VERSION}"

# ── 6. Create GitHub Release ─────────────────────────────────────────────────
echo ""
echo "Creating GitHub release v${NEW_VERSION}..."
"$GH" release create "v${NEW_VERSION}" \
    "$TARBALL_PATH" \
    --repo "$GITHUB_REPO" \
    --title "v${NEW_VERSION}" \
    --notes "Release v${NEW_VERSION}"

rm -f "$TARBALL_PATH"

echo ""
echo "============================================"
echo " Released v${NEW_VERSION}"
echo " Pi will auto-update within 30 minutes."
echo " Force update: sudo systemctl start ficio-updater.service"
echo "============================================"
