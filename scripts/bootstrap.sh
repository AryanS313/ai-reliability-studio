#!/usr/bin/env bash
# Create or reuse a supported environment; never replace .venv or .env.
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
requirements_file="requirements.txt"
check_only=false
for option in "$@"; do
    case "$option" in
        --dev) requirements_file="requirements-dev.txt" ;;
        --check) check_only=true ;;
        --help|-h)
            printf '%s\n' 'Usage: bash scripts/bootstrap.sh [--dev] [--check]' \
                'PYTHON_BIN selects Python 3.11 or 3.12 when creating a new .venv.' \
                'An existing supported .venv is reused. No .env file is created or changed.'
            exit 0
            ;;
        *) printf 'Unknown option: %s\n' "$option" >&2; exit 2 ;;
    esac
done

supported_python() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)'
}

venv_dir="$project_dir/.venv"
if [[ -e "$venv_dir" || -L "$venv_dir" ]]; then
    if [[ ! -x "$venv_dir/bin/python" ]] || ! supported_python "$venv_dir/bin/python"; then
        printf '%s\n' 'Existing .venv is unusable or is not Python 3.11/3.12. It has been preserved.' \
            'Choose an unused backup location and move it yourself before running bootstrap again.' >&2
        exit 1
    fi
    python_command="$venv_dir/bin/python"
else
    python_command="${PYTHON_BIN:-}"
    if [[ -z "$python_command" ]]; then
        for candidate in python3.12 python3.11 python3; do
            if command -v "$candidate" >/dev/null 2>&1 && supported_python "$candidate"; then
                python_command="$candidate"
                break
            fi
        done
    fi
    if [[ -z "$python_command" ]] || ! command -v "$python_command" >/dev/null 2>&1 || ! supported_python "$python_command"; then
        printf '%s\n' 'Python 3.11 or 3.12 is required. Install a supported CPython build and set PYTHON_BIN to its executable.' >&2
        exit 1
    fi
fi

"$python_command" --version
if [[ "$check_only" == true ]]; then
    printf '%s\n' 'Bootstrap preflight passed. No environment or configuration files were changed.'
    exit 0
fi
if [[ ! -e "$venv_dir" ]]; then
    "$python_command" -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install -r "$project_dir/$requirements_file"
"$venv_dir/bin/python" -m pip check
printf '%s\n' 'Environment ready. Existing .env values were preserved.' \
    'Sample: APP_ACCESS_MODE=public-demo .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1' \
    'Private: APP_ACCESS_MODE=local .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1'
