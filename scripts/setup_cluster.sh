#!/bin/bash
# scripts/setup_cluster.sh
# This script helps build the neuro-mod Singularity container.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "--------------------------------------------------"
echo "fMRI-pipeline-core: Singularity Build Tool"
echo "--------------------------------------------------"

if ! command -v singularity &> /dev/null; then
    echo "ERROR: Singularity not found on this machine."
    echo "Please run this on a machine with Singularity installed (e.g., restricted cluster) or build locally and upload."
    exit 1
fi

IMAGE_NAME="neuro-mod.sif"
DEF_FILE="neuro-mod.def"

echo "[1/2] Building $IMAGE_NAME from $DEF_FILE..."
# Note: On many clusters, you might need --fakeroot or run on a build node
if [ "$EUID" -ne 0 ]; then
    echo "Warning: Not running as root. Attempting build with --fakeroot..."
    singularity build --fakeroot "$IMAGE_NAME" "$DEF_FILE"
else
    singularity build "$IMAGE_NAME" "$DEF_FILE"
fi

echo "[2/2] Verifying container..."
singularity run "$IMAGE_NAME" --help

echo "--------------------------------------------------"
echo "SUCCESS: $IMAGE_NAME is ready."
echo "Workflow:"
echo "1. Edit configs/server_test.yaml"
echo "2. Run: singularity run $IMAGE_NAME bids prepare --config configs/server_test.yaml"
echo "--------------------------------------------------"
