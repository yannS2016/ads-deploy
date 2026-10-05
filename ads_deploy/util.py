import logging
import os
import pathlib
import re
import string

import pytmc

logger = logging.getLogger(__name__)

ADS_IOC_LOCATION = pathlib.Path(
    os.environ.get('ADS_IOC_LOCATION', r'C:\Repos\ads-ioc')
)


def parse_version_tag(name):
    """
    Parse a version-like tag or directory name (e.g. ``R2.1.3``, ``v1.0``)
    into a tuple of ints suitable for numeric sorting/``max()``.

    Returns ``None`` if ``name`` isn't a purely-numeric dotted version (e.g.
    ``master``, a pre-release tag like ``R2.1.3-rc1``, or any other
    non-version ref/tag) -- every part must be numeric so the result is
    always safe to compare/sort against another parsed tuple.
    """
    try:
        version = name.lstrip('Rv').replace('-', '.')
        parts = version.split('.')
        if parts and all(part.isdigit() for part in parts):
            return tuple(int(part) for part in parts)
    except Exception:
        ...

    return None


def get_latest_ads_ioc():
    """
    Get the latest ADS IOC path based on environment settings.

    Returns
    -------
    pathlib.Path
    """
    if not ADS_IOC_LOCATION.exists():
        raise RuntimeError(
            f'ADS_IOC_LOCATION={ADS_IOC_LOCATION} does not exist.  Cannot '
            'automatically find latest version of ads-ioc.'
        )

    if (ADS_IOC_LOCATION / 'iocBoot' / 'templates').exists():
        return ADS_IOC_LOCATION

    paths = {
        parse_version_tag(path.name): path for path in ADS_IOC_LOCATION.iterdir()
        if parse_version_tag(path.name) is not None
    }

    if not paths:
        raise RuntimeError(
            f'No versions in ADS_IOC_LOCATION={ADS_IOC_LOCATION} were found. '
            'Cannot automatically find latest version of ads-ioc.'
        )

    latest_version = paths[max(paths)]
    if (latest_version / 'iocBoot' / 'templates').exists():
        logger.info('Found latest ads-ioc: %s', latest_version)
        return latest_version

    raise RuntimeError(
        f'The latest version in ADS_IOC_LOCATION={ADS_IOC_LOCATION} was '
        f'determined to be {max(paths)} ({latest_version}), but there is no '
        'corresponding Makefile.  Cannot automatically find latest version of '
        'ads-ioc.'
    )


def get_tsprojects_from_filename(filename):
    """
    From a TwinCAT solution (.sln) or .tsproj, return all tsproj projects.

    Returns
    -------
    root : pathlib.Path
        Project root directory (where the solution or provided tsproj is
        located).

    projects : list
        List of tsproj projects.
    """
    filename = pathlib.Path(filename).resolve()
    if filename.suffix == '.tsproj':
        return filename.parent, [filename]
    if filename.suffix == '.sln':
        return filename.parent, pytmc.parser.projects_from_solution(filename)

    raise RuntimeError(f'Expected a .tsproj/.sln file; got {filename.suffix}')


def split_macros(macros):
    """Split user-provided macro strings into a dictionary."""
    split = [macro.split('=', 1) for macro in macros]
    return {var: value for var, value in split}


def expand_macros(s, macros):
    if '$' not in s:
        return s

    if '$(' in s:
        # Replace $(...) with ${...} for string.Template
        s = re.sub(r'\$\(([^)]+)\)', r'${\1}', s)

    try:
        return string.Template(s).substitute(macros)
    except KeyError:
        raise ValueError(f'Unexpanded macro in string: {s}') from None


def should_filter(includes, excludes, values):
    excluded = any(excl in value
                   for excl in excludes
                   for value in values
                   )
    if excluded:
        return False

    return not len(includes) or any(incl in value
                                    for incl in includes
                                    for value in values
                                    )
