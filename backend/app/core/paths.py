"""Finding the repository's data files, from source or from a container image.

Three of these files are load-bearing at runtime — the risk weights, the label datasets,
and the fixture cache — and each was previously located by counting `..` from `__file__`.
That works exactly once, from a source checkout. In an image where the package is
installed into site-packages and the data files sit beside the working directory, the same
expression walks to `/` and silently resolves to a path that does not exist.

So this searches instead of assuming: the working directory first, because that is where a
container puts them, then upward from this module, because that is where a checkout puts
them. An absolute path is taken as given.

A missing file raises with the setting that controls it, because "no such file: /config/
risk_weights.yaml" tells an operator nothing about which environment variable to change.
"""

from pathlib import Path

_HERE = Path(__file__).resolve()


def resolve(relative: str, *, setting: str) -> Path:
    """Locate a repository data file, or say which setting points at nothing."""
    candidate = Path(relative)
    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"{setting} points at {candidate}, which does not exist")

    searched = [Path.cwd() / candidate]
    searched += [parent / candidate for parent in _HERE.parents]
    for path in searched:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"{setting} is {relative!r}, which was not found relative to the working "
        f"directory ({Path.cwd()}) or to the installed package. Set {setting} to an "
        f"absolute path, or run from a directory that contains it."
    )


def resolve_writable(relative: str) -> Path:
    """A directory this process writes to, created if it does not exist.

    Unlike `resolve`, absence is not an error: evidence and report directories are made
    on first use.
    """
    candidate = Path(relative)
    return candidate if candidate.is_absolute() else Path.cwd() / candidate
