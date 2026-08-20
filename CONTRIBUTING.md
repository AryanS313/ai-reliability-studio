# Contributing

1. Create a branch from the current default branch.
2. Install `requirements-dev.txt` in a Python 3.11 virtual environment.
3. Run `pre-commit install` if pre-commit is available.
4. Add behavioral tests for every evaluator, storage, target, or authorization
   change. Include counterexamples, not only happy paths.
5. Run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest`.
6. Document schema, metric, security, and compatibility implications.

Never commit keys, customer data, provider responses containing personal data,
or production database snapshots. Synthetic fixtures must be clearly labelled.
