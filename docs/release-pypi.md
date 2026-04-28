# PyPI Release Checklist

This project publishes the Python package from GitHub Actions using PyPI
Trusted Publishing. No PyPI API token is required.

## One-Time Setup

1. On PyPI, add a pending trusted publisher for `instacalendar`.
2. Use these publisher values:
   - Owner: `lkoelman`
   - Repository: `instacalendar`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. In GitHub, create the `pypi` environment.
4. Configure required reviewers on the `pypi` environment if release approval
   should be manual.

## Release

1. Update `version` in `pyproject.toml`.
2. Run local checks:

   ```bash
   uv run ruff check
   uv run pytest
   uv build
   uv run --with twine twine check dist/*
   uvx check-wheel-contents dist/*.whl
   ```

3. Commit the release change after reviewing docs and package metadata.
4. Create and push a matching version tag, for example:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

5. Approve the `pypi` environment deployment in GitHub Actions when prompted.
6. Confirm the package page and install path:

   ```bash
   uvx instacalendar --help
   ```

The tag must match the package version. For example, tag `v0.1.0` publishes
`version = "0.1.0"`.
