"""
`ads-deploy summary` runs `pytmc summary --all --code --markdown` for a
solution, writes it to a file, and opens it. Replaces the old `summary.cmd`,
called directly as a Visual Studio External Tool (Command=ads-deploy,
Arguments="summary $(SolutionDir)$(SolutionFileName)") with no `.cmd`
wrapper needed.
"""

import argparse
import logging
import os
import subprocess

from . import vstools

DESCRIPTION = __doc__
logger = logging.getLogger(__name__)


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "solution",
        type=str,
        help="Full solution path, e.g. $(SolutionDir)$(SolutionFileName)",
    )

    return parser


def main(solution: str) -> None:
    solution = vstools.resolve_solution(solution)
    env = vstools.tool_env("pytmc")
    pytmc = vstools.resolve_executable("pytmc", env)

    output_path = solution.parent / f"{solution.stem}.summary.txt"

    with open(output_path, "w") as f:
        result = subprocess.run(
            [pytmc, "summary", "--all", "--code", "--markdown", str(solution)],
            stdout=f,
            env=env,
        )

    if result.returncode != 0 or not output_path.exists():
        logger.error("Project summary not generated! Check for errors above.")
        raise SystemExit(1)

    os.startfile(output_path)  # noqa: used on Windows only
