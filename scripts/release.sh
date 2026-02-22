#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT_FILE="$ROOT_DIR/app/pyproject.toml"
CHANGELOG_FILE="$ROOT_DIR/CHANGELOG.md"
CHANGELOG_TEMPLATE="$ROOT_DIR/docs/CHANGELOG_TEMPLATE.md"
RELEASE_NOTES_DIR="$ROOT_DIR/docs/releases"

DRY_RUN=0
ALLOW_DIRTY=0
DO_COMMIT=1
DO_TAG=1
BUMP_KIND=""
TARGET_VERSION=""

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh --bump patch|minor|major [--dry-run]
  scripts/release.sh --version X.Y.Z [--dry-run]

Options:
  --bump <patch|minor|major>  Auto bump version from current pyproject version.
  --version <X.Y.Z>           Set target version directly.
  --dry-run                   Show planned actions without modifying files.
  --allow-dirty               Allow running with uncommitted changes.
  --no-commit                 Do not create release commit.
  --no-tag                    Do not create git tag.
  -h, --help                  Show this help.
EOF
}

die() {
  echo "[release] $*" >&2
  exit 1
}

is_semver() {
  [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump)
      [[ $# -ge 2 ]] || die "--bump requires a value"
      BUMP_KIND="$2"
      shift 2
      ;;
    --version)
      [[ $# -ge 2 ]] || die "--version requires a value"
      TARGET_VERSION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --no-commit)
      DO_COMMIT=0
      shift
      ;;
    --no-tag)
      DO_TAG=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -f "$PYPROJECT_FILE" ]] || die "missing $PYPROJECT_FILE"
[[ -f "$CHANGELOG_TEMPLATE" ]] || die "missing $CHANGELOG_TEMPLATE"

if [[ -n "$BUMP_KIND" && -n "$TARGET_VERSION" ]]; then
  die "use either --bump or --version, not both"
fi

if [[ -z "$BUMP_KIND" && -z "$TARGET_VERSION" ]]; then
  die "missing target version: use --bump or --version"
fi

if [[ -n "$BUMP_KIND" && "$BUMP_KIND" != "patch" && "$BUMP_KIND" != "minor" && "$BUMP_KIND" != "major" ]]; then
  die "invalid --bump value: $BUMP_KIND"
fi

CURRENT_VERSION="$(python3 - "$PYPROJECT_FILE" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
if not match:
    raise SystemExit("version_not_found")
print(match.group(1))
PY
)"

if [[ -z "$TARGET_VERSION" ]]; then
  IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
  case "$BUMP_KIND" in
    patch)
      PATCH="$((PATCH + 1))"
      ;;
    minor)
      MINOR="$((MINOR + 1))"
      PATCH=0
      ;;
    major)
      MAJOR="$((MAJOR + 1))"
      MINOR=0
      PATCH=0
      ;;
  esac
  TARGET_VERSION="${MAJOR}.${MINOR}.${PATCH}"
fi

is_semver "$CURRENT_VERSION" || die "current version is not semver: $CURRENT_VERSION"
is_semver "$TARGET_VERSION" || die "target version is not semver: $TARGET_VERSION"
[[ "$CURRENT_VERSION" != "$TARGET_VERSION" ]] || die "target version equals current version"

cd "$ROOT_DIR"

if [[ $ALLOW_DIRTY -ne 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree is not clean; commit/stash first or use --allow-dirty"
  fi
fi

if [[ $DO_TAG -eq 1 && $DO_COMMIT -eq 0 ]]; then
  die "--no-commit cannot be used with tag creation; use --no-tag as well"
fi

DATE_UTC="$(date -u +%F)"
TAG_NAME="v${TARGET_VERSION}"
RELEASE_NOTES_FILE="$RELEASE_NOTES_DIR/${TAG_NAME}.md"

echo "[release] current version: $CURRENT_VERSION"
echo "[release] target version : $TARGET_VERSION"
echo "[release] release tag    : $TAG_NAME"
echo "[release] notes file     : $RELEASE_NOTES_FILE"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[release] dry-run only, no files modified."
  exit 0
fi

python3 - "$PYPROJECT_FILE" "$TARGET_VERSION" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
new_version = sys.argv[2]
text = path.read_text(encoding="utf-8")
updated, count = re.subn(
    r'(?m)^version\s*=\s*"[^"]+"\s*$',
    f'version = "{new_version}"',
    text,
    count=1,
)
if count != 1:
    raise SystemExit("version_update_failed")
path.write_text(updated, encoding="utf-8")
PY

mkdir -p "$RELEASE_NOTES_DIR"

python3 - "$CHANGELOG_TEMPLATE" "$RELEASE_NOTES_FILE" "$TARGET_VERSION" "$DATE_UTC" "$CURRENT_VERSION" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
target = Path(sys.argv[2])
version = sys.argv[3]
date_utc = sys.argv[4]
previous = sys.argv[5]

content = (
    template.replace("__VERSION__", version)
    .replace("__DATE__", date_utc)
    .replace("__PREVIOUS_VERSION__", previous)
)
target.write_text(content, encoding="utf-8")
PY

if [[ ! -f "$CHANGELOG_FILE" ]]; then
  cat > "$CHANGELOG_FILE" <<'EOF'
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
EOF
fi

python3 - "$CHANGELOG_FILE" "$TAG_NAME" "$DATE_UTC" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
tag = sys.argv[2]
date_utc = sys.argv[3]

section = (
    f"\n## [{tag}] - {date_utc}\n\n"
    "### Added\n\n- TODO\n\n"
    "### Changed\n\n- TODO\n\n"
    "### Fixed\n\n- TODO\n"
)

text = path.read_text(encoding="utf-8")
if f"## [{tag}]" not in text:
    path.write_text(text.rstrip() + section + "\n", encoding="utf-8")
PY

if [[ $DO_COMMIT -eq 1 ]]; then
  git add "$PYPROJECT_FILE" "$CHANGELOG_FILE" "$RELEASE_NOTES_FILE"
  git commit -m "release: ${TAG_NAME}"
  echo "[release] commit created."
else
  echo "[release] commit skipped (--no-commit)."
fi

if [[ $DO_TAG -eq 1 ]]; then
  git tag -a "$TAG_NAME" -m "release ${TAG_NAME}"
  echo "[release] tag created: $TAG_NAME"
else
  echo "[release] tag skipped (--no-tag)."
fi

echo "[release] done."
echo "[release] next: git push origin <branch> && git push origin --tags"
