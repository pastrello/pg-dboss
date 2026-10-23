#!/usr/bin/env bash
# DBOSS unified installer: local by default; no PGDATA/ZFS changes.
set -Eeuo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
umask 077
MODE="${1:---setup}"
PREFIX="${DBOSS_PREFIX:-/opt/dboss}"

usage() {
  cat <<'EOF'
DBOSS — installer/test entry point
  ./install.sh                  Create local .venv, install package, run tests
  ./install.sh --setup          Same as above (no root, no PostgreSQL changes)
  ./install.sh --self-test      Run offline unit tests with available Python
  ./install.sh --doctor         Check environment without changes
  sudo ./install.sh --install   Install isolated DBOSS CLI under /opt/dboss/venv
  sudo ./install.sh --legacy-configure
                                Run original PG Intelligence guided setup;
                                may explicitly create only its telemetry objects
  ./install.sh --help

Environment: DBOSS_PYTHON selects Python >=3.9; DBOSS_PREFIX sets install destination.
Legacy service pgintel.service remains unchanged; none is auto-enabled.
EOF
}

select_python() {
  if [[ -n "${DBOSS_PYTHON:-}" ]]; then
    command -v "$DBOSS_PYTHON" >/dev/null 2>&1 || { echo "DBOSS_PYTHON not executable" >&2; exit 1; }
    printf '%s\n' "$DBOSS_PYTHON"
    return
  fi
  local c
  for c in python3.12 python3.13 python3.11 python3.10 python3.9 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$c"
      return
    fi
  done
  echo "Python >=3.9 required; on Rocky 8 install Python 3.12 first." >&2
  exit 1
}

run_tests() {
  local py="$1"
  PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" "$py" -m unittest discover -s tests -p 'test_*.py' -v
  "$py" -m dboss --version
  "$py" -m dboss --help >/dev/null
}

case "$MODE" in
  --setup)
    PY="$(select_python)"
    if [[ ! -x .venv/bin/python ]]; then "$PY" -m venv .venv; fi
    .venv/bin/python -m pip install -e .
    run_tests .venv/bin/python
    echo "Ready: .venv/bin/dboss --help"
    ;;
  --self-test|--test)
    PY="$(select_python)"
    if [[ -x .venv/bin/python ]]; then PY=".venv/bin/python"; fi
    run_tests "$PY"
    ;;
  --doctor)
    PY="$(select_python)"
    "$PY" --version
    if [[ -x .venv/bin/dboss ]]; then .venv/bin/dboss --version; fi
    if [[ -x "$PREFIX/venv/bin/dboss" ]]; then "$PREFIX/venv/bin/dboss" --version; fi
    if command -v cargo >/dev/null 2>&1; then cargo --version; else echo "Rust toolchain optional / not installed"; fi
    ;;
  --install)
    [[ "$EUID" == 0 ]] || { echo "Use sudo for system installation (or use ./install.sh locally)" >&2; exit 1; }
    PY="$(select_python)"
    install -d -m 0750 "$PREFIX"
    if [[ ! -x "$PREFIX/venv/bin/python" ]]; then "$PY" -m venv "$PREFIX/venv"; fi
    "$PREFIX/venv/bin/python" -m pip install .
    "$PREFIX/venv/bin/dboss" --version
    echo "Installed in $PREFIX/venv (no service changes)."
    ;;
  --legacy-configure)
    [[ "$EUID" == 0 ]] || { echo "Legacy setup requires sudo" >&2; exit 1; }
    echo "WARNING: invoking original PG Intelligence guided installer."
    exec bash ./install-rocky.sh --configure
    ;;
  --help|-h|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
