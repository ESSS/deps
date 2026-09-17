# RELEASING

1. Create a new branch off `master` named `release-X.Y.Z`.
2. Update `CHANGELOG.md`.
3. Update the version in `pyproject.toml` and run `uv sync`.
4. Open a PR from the `release-X.Y.Z` branch and merge it.
5. Tag the repository by creating a new [GitHub Release](https://github.com/ESSS/deps/releases).
