#!/usr/bin/env bash
# kf-install.sh — install KnowledgeForge as a CLI extension/plugin.
#
# Usage:
#   bash kf-install.sh <gemini|claude|codex> [--target <dir>]
#
# Idempotent: re-running overwrites manifests in place.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: kf-install.sh <gemini|claude|codex> [--target <dir>]

Installs KnowledgeForge as an extension/plugin for the chosen CLI by copying
the relevant manifest and skills into the CLI's plugin directory.

Targets (defaults):
  gemini  ->  ${HOME}/.gemini/extensions/knowledgeforge
  claude  ->  ${HOME}/.claude/plugins/knowledgeforge
  codex   ->  ${HOME}/.codex/plugins/knowledgeforge

Options:
  --target <dir>   Override the destination directory.

Prerequisite: pip install -e <repo>/kb-mcp-server
Required env at runtime: BACKEND_URL (URL of the kb-agent backend).
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

TARGET_CLI="$1"
shift
CUSTOM_TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      CUSTOM_TARGET="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "kf-install: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$TARGET_CLI" in
  gemini)
    MANIFEST_SRC="${REPO_ROOT}/gemini-extension.json"
    MANIFEST_NAME="gemini-extension.json"
    DEFAULT_DEST="${HOME}/.gemini/extensions/knowledgeforge"
    NEXT_STEP_HINT='Restart Gemini CLI, then run: gemini /mcp   (you should see "knowledgeforge")'
    ;;
  claude)
    MANIFEST_SRC="${REPO_ROOT}/.claude-plugin/plugin.json"
    MANIFEST_NAME="plugin.json"
    DEFAULT_DEST="${HOME}/.claude/plugins/knowledgeforge"
    NEXT_STEP_HINT='Restart Claude Code, then check: /plugins   (you should see "knowledgeforge")'
    ;;
  codex)
    MANIFEST_SRC="${REPO_ROOT}/.codex-plugin/plugin.json"
    MANIFEST_NAME="plugin.json"
    DEFAULT_DEST="${HOME}/.codex/plugins/knowledgeforge"
    NEXT_STEP_HINT='Restart Codex CLI; verify the knowledgeforge MCP server is registered.'
    ;;
  *)
    echo "kf-install: unknown CLI '${TARGET_CLI}' (expected: gemini|claude|codex)" >&2
    usage
    exit 2
    ;;
esac

DEST="${CUSTOM_TARGET:-${DEFAULT_DEST}}"

if [[ ! -f "$MANIFEST_SRC" ]]; then
  echo "kf-install: manifest not found at ${MANIFEST_SRC}" >&2
  exit 1
fi

echo "kf-install: installing KnowledgeForge for ${TARGET_CLI}"
echo "  source : ${REPO_ROOT}"
echo "  dest   : ${DEST}"

mkdir -p "${DEST}"
cp -f "${MANIFEST_SRC}" "${DEST}/${MANIFEST_NAME}"

# Copy skills directory (idempotent overwrite).
if [[ -d "${REPO_ROOT}/skills" ]]; then
  mkdir -p "${DEST}/skills"
  cp -Rf "${REPO_ROOT}/skills/." "${DEST}/skills/"
fi

cat <<EOF

OK — installed:
  ${DEST}/${MANIFEST_NAME}
  ${DEST}/skills/knowledgeforge-architecture/SKILL.md

Next steps:
  1. Ensure the Python entrypoint is installed:
       pip install -e ${REPO_ROOT}/kb-mcp-server
  2. Export BACKEND_URL (and optionally KF_TENANT):
       export BACKEND_URL=https://kb-agent-XXXX.run.app
  3. ${NEXT_STEP_HINT}
EOF
