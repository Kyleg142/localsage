#!/usr/bin/env fish

# Documentation is located in TOOLS.md

function cleanup
    rm -rf ./dist ./localsage.egg-info ./.venv
    trap - EXIT INT
end
trap cleanup EXIT INT

set -l project_root (realpath (status dirname)/..);

cd $project_root; or return 1
python3 -m venv .venv; or return 1

set -l venv_pip $project_root/.venv/bin/pip;
set -l venv_python $project_root/.venv/bin/python3;

$venv_pip install build; or return 1
$venv_python -m build; or return 1
$venv_pip install dist/localsage-*.whl --force-reinstall; or return 1
$project_root/.venv/bin/localsage
cleanup
