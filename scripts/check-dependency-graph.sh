#!/usr/bin/env bash
#
# Decide whether actions/dependency-review-action can run on this repository.
#
# The action needs the repository's Dependency graph. When the setting is off,
# the action fails every pull request with "Dependency review is not supported
# on this repository" -- a repository setting, not a defect in the change under
# review. This probe asks GitHub's SBOM endpoint, which is served from the
# dependency graph and answers 404 when it is disabled, and writes
# `enabled=true|false` to $GITHUB_OUTPUT so the review step can be skipped
# with a visible warning instead of failing the pipeline.
#
# Unknown is never "disabled": a timeout, a rate limit, or any other status
# leaves enabled=true, so the review still runs and reports its own verdict.

set -u

REPOSITORY="${REPOSITORY:-${GITHUB_REPOSITORY:-}}"
API_URL="${GITHUB_API_URL:-https://api.github.com}"
SERVER_URL="${GITHUB_SERVER_URL:-https://github.com}"
CURL_TIMEOUT="${DEPENDENCY_GRAPH_CURL_TIMEOUT:-30}"

if [ -z "$REPOSITORY" ]; then
  printf 'REPOSITORY (or GITHUB_REPOSITORY) must name the owner/repo to probe\n' >&2
  exit 2
fi

emit() {
  printf 'enabled=%s\n' "$1"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'enabled=%s\n' "$1" >> "$GITHUB_OUTPUT"
  fi
}

auth=()
if [ -n "${GH_TOKEN:-}" ]; then
  auth=(-H "Authorization: Bearer ${GH_TOKEN}")
fi

status=$(curl -sS --max-time "$CURL_TIMEOUT" -o /dev/null -w '%{http_code}' \
  "${auth[@]}" \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "${API_URL}/repos/${REPOSITORY}/dependency-graph/sbom" 2>/dev/null)

case "$status" in
  200)
    printf 'Dependency graph is enabled for %s.\n' "$REPOSITORY"
    emit true
    ;;
  404)
    settings="${SERVER_URL}/${REPOSITORY}/settings/security_analysis"
    message="Dependency graph is disabled for ${REPOSITORY}, so dependency review was skipped. Enable it at ${settings} to review dependency changes on pull requests."
    printf '::warning title=Dependency review skipped::%s\n' "$message"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
      printf '### Dependency review skipped\n\n%s\n' "$message" >> "$GITHUB_STEP_SUMMARY"
    fi
    emit false
    ;;
  *)
    printf 'The dependency graph probe answered %s; running dependency review anyway.\n' \
      "${status:-no status}"
    emit true
    ;;
esac

exit 0
