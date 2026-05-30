# homebrew-tap

Homebrew tap for [`rossum-user-loader`](https://github.com/siarhei-leuchanka/rossum-user-loader).

> **This folder is a template for a *separate* GitHub repo.** Copy its contents
> into a new public repo named **`homebrew-tap`** under your GitHub account
> (`github.com/siarhei-leuchanka/homebrew-tap`). The `homebrew-` prefix is
> required; the `tap` part is what users type.

## Install

```bash
brew install siarhei-leuchanka/tap/rossum-user-loader
```

Homebrew auto-clones this tap repo, reads `Formula/rossum-user-loader.rb`, and
builds the tool into an isolated virtualenv.

## Releasing a new version

1. In the **app repo** (`rossum-user-loader`), bump `version` in
   `pyproject.toml` and `src/rossum_user_loader/__init__.py`, commit.
2. Tag and push:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
   Then create a GitHub Release for that tag (the `archive/refs/tags/...tar.gz`
   URL is generated automatically by GitHub for any tag).
3. Compute the tarball checksum:
   ```bash
   curl -L https://github.com/siarhei-leuchanka/rossum-user-loader/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
   ```
4. In **this tap repo**, update `url` (the version) and `sha256` in
   `Formula/rossum-user-loader.rb`, commit, push.
5. Verify: `brew update && brew upgrade rossum-user-loader`.

## Notes

- The formula installs dependencies via `pip` from PyPI at install time. This
  is convenient but not offline-reproducible (`brew audit --strict` will warn).
  Acceptable for a personal/internal tap. See the comment block in the formula
  for how to switch to pinned `resource` stanzas later.
```
