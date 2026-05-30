# Homebrew formula for rossum-user-loader.
#
# This file lives in the tap repo: github.com/siarhei-leuchanka/homebrew-tap
# (path: Formula/rossum-user-loader.rb). Users install with:
#
#     brew install siarhei-leuchanka/tap/rossum-user-loader
#
# Source: a GitHub release tarball of the app repo (no PyPI publish needed).
# Dependencies (rossum-api, openpyxl, and their transitive deps) are resolved
# by pip from PyPI at install time, into a private venv under libexec — the
# same hidden isolation pipx uses. Users never manage a venv.
#
# Trade-off: installing via pip (rather than declared `resource` blocks) means
# the build is not fully offline/pinned, which `brew audit` flags. That is fine
# for a personal/internal tap. To make it audit-clean later, run
# `brew update-python-resources` to generate resource stanzas and switch
# `install` to `virtualenv_install_with_resources`.

class RossumUserLoader < Formula
  include Language::Python::Virtualenv

  desc "Bulk-load users into Rossum from a spreadsheet"
  homepage "https://github.com/siarhei-leuchanka/rossum-user-loader"
  url "https://github.com/siarhei-leuchanka/rossum-user-loader/archive/refs/tags/v0.1.0.tar.gz"
  # Fill after tagging: curl -L <url above> | shasum -a 256
  sha256 "PLACEHOLDER_FILL_AFTER_TAGGING_v0_1_0"
  license "MIT"

  depends_on "python@3.12"

  def install
    # Private virtualenv; pip resolves deps from PyPI (wheels) at install time.
    venv = virtualenv_create(libexec, "python3.12")
    system libexec/"bin/python", "-m", "pip", "install", "--upgrade", "pip"
    system libexec/"bin/python", "-m", "pip", "install", buildpath
    bin.install_symlink libexec/"bin/rossum-user-loader"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/rossum-user-loader --version")
  end
end
