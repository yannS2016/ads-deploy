#!/bin/bash

set -e
export LC_ALL=C

die() { echo "ERROR: $*" >&2; exit 1; }

SCRIPT_PATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
WINDOWS_ADS_IOC_TOP="$1"

source /c/miniconda/etc/profile.d/conda.sh

source "${SCRIPT_PATH}/conda_config.sh"
conda activate $ADS_DEPLOY_CONDA_ENV

CONDA_ENV_PATH="${CONDA_PREFIX:-}"
if [[ -z "$CONDA_ENV_PATH" ]]; then
    die "CONDA_PREFIX is not set. Please activate your conda env first!"
fi

# Find the correct Python binary inside the environment
PYTHON="$(conda run -n $ADS_DEPLOY_CONDA_ENV which python 2>/dev/null || which python)"
PYTHON_BASENAME="$(basename "$PYTHON")"

if [[ -z "$PYTHON" || ! -f "$PYTHON" ]]; then
    die "Active python executable not found!"
fi

PYTHON3="$(dirname "$PYTHON")/python3${PYTHON_BASENAME#python}"

if [[ ! -f "$PYTHON3" ]]; then
    if [[ "$OSTYPE" =~ "msys" || "$OSTYPE" =~ "cygwin" || "$PYTHON_BASENAME" =~ ".exe" ]]; then
        cp "$PYTHON" "$PYTHON3" || die "Unable to copy $PYTHON to $PYTHON3"
        echo "Copied $PYTHON to $PYTHON3"
    else
        ln -s "$PYTHON" "$PYTHON3" || die "Unable to symlink $PYTHON to $PYTHON3"
        echo "Symlinked $PYTHON to $PYTHON3"
    fi
fi

# 2. Clone or update the master branch
MASTER_DIR="${WINDOWS_ADS_IOC_TOP}/master"
REPO_URL="https://github.com/pcdshub/ioc-common-ads-ioc.git"

if [[ -d "$MASTER_DIR/.git" ]]; then
    cd "$MASTER_DIR"
    git status > /dev/null 2>&1 || die "Git repo not valid: $MASTER_DIR"
    git checkout master
    git pull origin master
    echo "Master branch updated."
else
    mkdir -p "${WINDOWS_ADS_IOC_TOP}"
    git clone "$REPO_URL" "$MASTER_DIR"
    echo "Master branch cloned."
fi

# 3. Get latest release tag from GitHub
LATEST_TAG="$(curl -s https://api.github.com/repos/pcdshub/ioc-common-ads-ioc/releases/latest | grep -o '"tag_name": *"[^"]*"' | sed 's/"tag_name": *"//;s/"//g')"

echo "Latest tag is: $LATEST_TAG"

RELEASE_DIR="${WINDOWS_ADS_IOC_TOP}/${LATEST_TAG}"

# 4. Clone or update the release branch
if [[ -d "$RELEASE_DIR/.git" ]]; then
    cd "$RELEASE_DIR"
    git status > /dev/null 2>&1 || die "Git repo not valid: $RELEASE_DIR"
    git checkout "$LATEST_TAG"
    git pull origin "$LATEST_TAG"
    echo "Release $LATEST_TAG updated."
else
    mkdir -p "${WINDOWS_ADS_IOC_TOP}"
    git clone --single-branch --branch "$LATEST_TAG" "$REPO_URL" "$RELEASE_DIR"
    echo "Release $LATEST_TAG cloned."
fi

# 5. Update conda_config.cmd with the latest path (one replacement, add blank line)
CONFIG_FILE="$SCRIPT_PATH/conda_config.cmd"
TEMP_CONFIG="${CONFIG_FILE}.tmp"

LATEST_IOC_TOP="c:/Repos/ads-ioc/$LATEST_TAG"

if [[ ! -d "${WINDOWS_ADS_IOC_TOP}/${LATEST_TAG}" ]] || [[ -z "$LATEST_TAG" ]]; then
    LATEST_IOC_TOP="c:/Repos/ads-ioc/master"
fi

awk -v new_path="$LATEST_IOC_TOP" '
    BEGIN { replaced=0 }
    /WINDOWS_ADS_IOC_TOP=/ && replaced==0 {
        print "SET WINDOWS_ADS_IOC_TOP=" new_path
        print ""
        replaced=1
        next
    }
    { print }
' "$CONFIG_FILE" > "$TEMP_CONFIG"

mv "$TEMP_CONFIG" "$CONFIG_FILE"
echo "Updated $CONFIG_FILE with WINDOWS_ADS_IOC_TOP=$LATEST_IOC_TOP"

# echo "All steps complete."