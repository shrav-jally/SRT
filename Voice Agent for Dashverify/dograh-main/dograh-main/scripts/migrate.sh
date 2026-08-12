#!/usr/bin/env bash

set -e  # Exit immediately if a command exits with a non-zero status

# Set PYTHONPATH to the parent directory of the script's location
export PYTHONPATH="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

# Define color codes
RED='\033[0;31m'
NC='\033[0m' # No Color

env_file="api/.env"

# Check if environment file exists
if [ ! -f "$env_file" ]; then
    echo -e "${RED}Error: Environment file $env_file not found.${NC}"
    exit 1
fi

# Load environment variables
export $(grep -v '^#' "$env_file" | xargs)

# Run migrations
alembic -c api/alembic.ini upgrade head

# Create initial data in DB
# python api/initial_data.py