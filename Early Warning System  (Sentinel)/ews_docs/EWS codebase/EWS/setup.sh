#!/bin/bash
# Setup script for Annual Report Extraction Agent
# Installs all required Python dependencies

set -e

echo "=== Installing dependencies for Annual Report Extraction Agent ==="

# Install pip if not available
if ! python3 -m pip --version &>/dev/null; then
    echo "pip not found, installing..."
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    python3 /tmp/get-pip.py --user
    rm -f /tmp/get-pip.py
fi

# Install required packages
echo "Installing Python packages..."
python3 -m pip install --user \
    pdfplumber \
    openpyxl \
    pandas \
    httpx \
    langchain-openai \
    langchain-core \
    rapidfuzz \
    tabulate

echo ""
echo "=== Setup complete ==="
echo "Run: python3 run_extraction.py --pdf 'GODREJ PROPERTIES/Annual_Report_-W-7582679.pdf' --template 'Entities for extraction.xlsx'"
