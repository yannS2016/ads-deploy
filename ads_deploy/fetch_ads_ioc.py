"""
`ads-deploy fetch-ads-ioc` clones/updates the ads-ioc common IOC repository
and its latest release tag under a configured root directory, replacing the
old `post_install.sh` (which additionally self-mutated `conda_config.cmd` --
this command instead just prints the resolved path; nothing needs to cache
it, since `ads-deploy build` resolves the latest local ads-ioc version fresh
each time via `util.get_latest_ads_ioc()`, the same way `ads-deploy iocboot`
already does).
"""

import argparse
import logging
import pathlib
import subprocess

from .util import parse_version_tag

logger = logging.getLogger(__name__)

DESCRIPTION = __doc__

REPO_URL = "https://github.com/pcdshub/ioc-common-ads-ioc.git"
DEFAULT_ROOT = pathlib.Path(r"C:\Repos\ads-ioc")


def _run(*args, **kwargs):
    logger.debug("$ %s", " ".join(args[0]))
    return subprocess.run(*args, check=True, **kwargs)


def _clone_or_update(
    directory: pathlib.Path, ref: str, single_branch: bool = False
) -> None:
    if (directory / ".git").exists():
        _run(["git", "-c", "advice.detachedHead=false", "checkout", ref], cwd=directory)
        _run(["git", "pull", "origin", ref], cwd=directory)
        logger.info("%s updated at %s", ref, directory)
    else:
        directory.parent.mkdir(parents=True, exist_ok=True)
        args = ["git", "-c", "advice.detachedHead=false", "clone"]
        if single_branch:
            args += ["--single-branch", "--branch", ref]
        args += [REPO_URL, str(directory)]
        _run(args)
        logger.info("%s cloned to %s", ref, directory)


def get_latest_release_tag() -> str:
    """
    Resolve the latest release tag via ``git ls-remote --tags``, sorted
    numerically (not lexicographically -- "R1.10.0" must sort after
    "R1.9.0", which plain string sorting gets wrong).
    """
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", REPO_URL],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = [
        line.rsplit("refs/tags/", 1)[-1]
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    versioned = {
        tag: parse_version_tag(tag)
        for tag in tags
        if parse_version_tag(tag) is not None
    }
    if not versioned:
        raise RuntimeError(f"No version-like tags found in {REPO_URL}")

    return max(versioned, key=versioned.get)


def fetch(root: pathlib.Path) -> pathlib.Path:
    """
    Clone/update the master branch and the latest release tag of ads-ioc
    under ``root``.  Returns the path of the fetched release.
    """
    root = pathlib.Path(root)

    _clone_or_update(root / "master", "master")

    latest_tag = get_latest_release_tag()
    logger.info("Latest ads-ioc release tag: %s", latest_tag)

    release_dir = root / latest_tag
    _clone_or_update(release_dir, latest_tag, single_branch=True)

    return release_dir


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "--root",
        type=str,
        default=str(DEFAULT_ROOT),
        help=f"Root directory to clone ads-ioc under (default: {DEFAULT_ROOT})",
    )
    return parser


def main(root: str) -> None:
    release_dir = fetch(pathlib.Path(root))
    print(release_dir)
