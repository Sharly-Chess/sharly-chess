"""Checks the installed application from inside the Flatpak Platform runtime.

The build runs against the SDK, whose Python packages pip treats as already
installed, but users run the application on the Platform runtime, which lacks
some of them. Run with:

    flatpak run --command=python3 --filesystem=<checkout> com.sharlychess.SharlyChess \
        <checkout>/scripts/export/linux/flatpak/scripts/check_runtime.py
"""

import importlib.metadata
import sys

from packaging.requirements import Requirement


def unresolved_requirements() -> list[str]:
    unresolved: set[str] = set()
    for distribution in importlib.metadata.distributions():
        for requirement_string in distribution.requires or []:
            requirement = Requirement(requirement_string)
            if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
                continue
            try:
                importlib.metadata.distribution(requirement.name)
            except importlib.metadata.PackageNotFoundError:
                unresolved.add(
                    f'{requirement.name} (required by {distribution.metadata["Name"]})'
                )
    return sorted(unresolved)


def main() -> int:
    unresolved = unresolved_requirements()
    if unresolved:
        print('Requirements missing from the Platform runtime:')
        for requirement in unresolved:
            print(f'  {requirement}')
        return 1

    sys.argv = ['sharly-chess', '--path', '/tmp/sharly-chess-runtime-check']
    from utils.scripts import init_script

    init_script()
    import web.server_engine  # noqa: F401

    print(
        'All requirements resolve and the application imports in the Platform runtime'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
