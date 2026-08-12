#!/usr/bin/env bash

set -e
set -x

mypy api
ruff check api --check
ruff format api --check