#!/usr/bin/env bash
# macOS double-click entry point. Finder runs a `.command` file in Terminal;
# it cannot run `run.sh` that way, hence this two-line wrapper rather than a
# second copy of the bootstrap logic.
cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
exec bash ./run.sh
