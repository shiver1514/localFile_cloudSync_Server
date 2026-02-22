#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TARGET_TAG=""
ROLLBACK_BRANCH=""
ALLOW_DIRTY=0
RESTART_SERVICE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/rollback_release.sh --target vX.Y.Z [options]

Options:
  --target <tag>        Target release tag/commit to rollback to (required).
  --branch <name>       Rollback branch name (default: rollback/<tag>-<timestamp>).
  --allow-dirty         Allow running with uncommitted changes.
  --restart-service     Restart localfile-cloudsync.service after checkout.
  --dry-run             Show planned actions without switching branches.
  -h, --help            Show this help.
EOF
}

die() {
  echo "[rollback] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || die "--target requires a value"
      TARGET_TAG="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a value"
      ROLLBACK_BRANCH="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --restart-service)
      RESTART_SERVICE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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

[[ -n "$TARGET_TAG" ]] || die "missing --target"

cd "$ROOT_DIR"
git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"
git rev-parse "${TARGET_TAG}^{commit}" >/dev/null 2>&1 || die "target not found: $TARGET_TAG"

if [[ $ALLOW_DIRTY -ne 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree is not clean; commit/stash first or use --allow-dirty"
  fi
fi

NOW_TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_BRANCH="backup/pre-rollback-${NOW_TS}"
SANITIZED_TAG="${TARGET_TAG#v}"

if [[ -z "$ROLLBACK_BRANCH" ]]; then
  ROLLBACK_BRANCH="rollback/${SANITIZED_TAG}-${NOW_TS}"
fi

if git show-ref --verify --quiet "refs/heads/${BACKUP_BRANCH}"; then
  die "backup branch already exists: ${BACKUP_BRANCH}"
fi

if git show-ref --verify --quiet "refs/heads/${ROLLBACK_BRANCH}"; then
  die "rollback branch already exists: ${ROLLBACK_BRANCH}"
fi

CURRENT_REF="$(git rev-parse --abbrev-ref HEAD)"
CURRENT_COMMIT="$(git rev-parse --short HEAD)"

echo "[rollback] current ref     : ${CURRENT_REF} (${CURRENT_COMMIT})"
echo "[rollback] target          : ${TARGET_TAG}"
echo "[rollback] backup branch   : ${BACKUP_BRANCH}"
echo "[rollback] rollback branch : ${ROLLBACK_BRANCH}"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[rollback] dry-run only, no branch switch performed."
  exit 0
fi

git branch "$BACKUP_BRANCH"
git switch -c "$ROLLBACK_BRANCH" "$TARGET_TAG"

if [[ $RESTART_SERVICE -eq 1 ]]; then
  systemctl --user restart localfile-cloudsync.service
fi

echo "[rollback] done."
echo "[rollback] backup branch retained at ${BACKUP_BRANCH}."
echo "[rollback] to return: git switch ${CURRENT_REF}"
