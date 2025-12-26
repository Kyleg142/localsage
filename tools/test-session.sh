#!/usr/bin/env bash

# Documentation is located in TOOLS.md

function cleanup {
    rm -rf ./dist ./localsage.egg-info ./.venv
    trap - EXIT INT
}
trap cleanup EXIT INT

PROJECT_ROOT=$(realpath "$(dirname "$0")/..")

cd "$PROJECT_ROOT" || exit 1
python3 -m venv .venv || exit 1

VENV_PIP="$PROJECT_ROOT/.venv/bin/pip"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"

"$VENV_PIP" install build || exit 1
"$VENV_PYTHON" -m build || exit 1
"$VENV_PIP" install dist/localsage-*.whl --force-reinstall || exit 1
"$PROJECT_ROOT/.venv/bin/localsage"
cleanup
