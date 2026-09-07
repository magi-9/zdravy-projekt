#!/usr/bin/env bash
set -e

echo "🐍 Backend"
cd backend
flake8 .
black --check .
isort --check-only .
mypy api --ignore-missing-imports
pytest --create-db --cov=api --cov=app --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=60
cd ..

echo "🌐 Frontend"
cd frontend
npm run lint
npm run test
