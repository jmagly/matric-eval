#!/usr/bin/env bash
# Validate a reviewed release commit and create its local annotated tag.
set -euo pipefail

usage() {
  echo "Usage: tools/release/cut-tag.sh YYYY.M.PATCH [--check] [--forge gitea|github]" >&2
  exit 2
}
[[ $# -ge 1 ]] || usage
version="$1"
shift
forge="gitea"
check_only=false
forge_set=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      [[ "$check_only" == false ]] || usage
      check_only=true
      shift
      ;;
    --forge)
      [[ $# -ge 2 && "$forge_set" == false ]] || usage
      case "$2" in
        gitea|github) forge="$2" ;;
        *) usage ;;
      esac
      forge_set=true
      shift 2
      ;;
    *) usage ;;
  esac
done
repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
python3 scripts/release_contract.py versions --expected "$version"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Release tagging requires a clean checkout, including untracked files." >&2
  exit 1
fi
test -f "docs/releases/${version}.md"
grep -Fq "## [${version}]" CHANGELOG.md
commit=$(git rev-parse HEAD)
python3 scripts/publish_forge_release.py verify-source \
  --forge "$forge" --commit "$commit" --root "$repo_root" --wait-seconds 900
if [[ "$commit" != "$(git rev-parse refs/remotes/origin/main)" ]]; then
  echo "Release tagging requires the exact current origin/main commit." >&2
  exit 1
fi
if git show-ref --verify --quiet "refs/tags/v${version}"; then
  echo "Local release tag already exists; do not replace published tags." >&2
  exit 1
fi
remote_tags=$(git ls-remote --tags origin "refs/tags/v${version}")
if [[ -n "$remote_tags" ]]; then
  echo "Remote release tag already exists; select the next CalVer patch." >&2
  exit 1
fi
if [[ "$check_only" == true ]]; then
  echo "Release source and CI verified; no tag created."
  exit 0
fi
git tag --annotate "v${version}" --message "matric-eval ${version}" "$commit"
echo "Created local tag v${version}. Review it, then push with:"
echo "git push origin refs/tags/v${version}"
