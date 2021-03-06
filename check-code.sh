#!/usr/bin/env bash
# Convenience script for running Travis-like checks.

set -eu
set -x

pep8 tests --max-line-length 120

pylint -j 2 --reports no eodatasets

# Run tests, taking coverage.
# Users can specify extra folders as arguments.
py.test --cov eodatasets --durations=5 eodatasets tests $@

