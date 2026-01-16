#!/bin/bash
set -e

echo 'Running tests...'
# Run specific test suites as requested
pytest -q app/api/tests
pytest -q app/langgraph_v2/tests
pytest -q app/services

# Or root if configured
# pytest -q .

echo 'All tests passed!'
