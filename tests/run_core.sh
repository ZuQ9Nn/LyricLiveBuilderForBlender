#!/bin/sh
# Runs tests/core with Blender's bundled Python (has numpy) from WSL.
# Set LLB_PY to use another Python 3.13 + numpy. Extra arguments go to unittest.
PY="${LLB_PY:-/mnt/c/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe}"
cd "$(dirname "$0")/.." || exit 1
PYTHONIOENCODING=utf-8 WSLENV="PYTHONIOENCODING${WSLENV:+:$WSLENV}" "$PY" -m unittest discover -s tests/core -t . "$@"
