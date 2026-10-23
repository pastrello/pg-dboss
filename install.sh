#!/usr/bin/env bash
# DBOSS entry point. Default mode only runs local tests; NEVER changes PGDATA/ZFS.
set -Eeuo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export PYTHONDONTWRITEBYTECODE=1
MODE="${1:---self-test}"
PREFIX="${DBOSS_PREFIX:-/opt/dboss}"
if [[ "${EUID}" == 0 ]]; then UMASK=027; else UMASK=077; fi
umask "$UMASK"
usage() {
  cat <<'EOF'
DBOSS 0.1.0 (PG Intelligence + DBOS)
  ./install.sh                 Run offline unit tests (non-destructive)
  ./install.sh --self-test     Run offline unit tests (non-destructive)
  ./install.sh --doctor        Check prerequisites/installed CLI (no writes)
  sudo ./install.sh --install  Install isolated DBOSS venv under /opt/dboss
  sudo ./install.sh --legacy-configure
                               Explicit PG Intelligence legacy setup/bootstrap
  ./install.sh --help
Environment: DBOSS_PREFIX changes install destination.
No systemd unit is enabled, no PG role/schema or ZFS property changed by --install.
Legacy installer is only invoked with --legacy-configure.
EOF
}
case "$MODE" in
  --self-test|--test)
    python3 -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m dboss --version
    python3 -m dboss --help >/dev/null
    ;;
  --doctor)
    command -v python3
    python3 --version
    if [[ -x "$PREFIX/venv/bin/dboss" ]]; then "$PREFIX/venv/bin/dboss" --version; fi
    if command -v cargo >/dev/null 2>&1; then cargo --version; else echo "Rust optional: cargo not installed"; fi
    ;;
  --install)
    command -v python3 >/dev/null
    command -v install >/dev/null
    install -d -m 0750 "$PREFIX"
    if [[ ! -d "$PREFIX/venv" ]]; then python3 -m venv "$PREFIX/venv"; fi
    "$PREFIX/venv/bin/python" -m pip install --upgrade pip
    "$PREFIX/venv/bin/python" -m pip install .
    "$PREFIX/venv/bin/dboss" --version
    echo "Installed. Run: $PREFIX/venv/bin/dboss --help"
    echo "Existing pgintel.service and /etc/pgintel are untouched."
    ;;
  --legacy-configure)
    echo "WARNING: PG Intelligence's original guided installer may create its own monitoring/repository objects."
    echo "Use only after reviewing install-rocky.sh and its production safety documentation."
    exec bash ./install-rocky.sh --configure
    ;;
  --help|-h|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
