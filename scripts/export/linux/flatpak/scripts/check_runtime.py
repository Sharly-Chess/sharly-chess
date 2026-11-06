"""Checks the installed application from inside the Flatpak Platform runtime.

The build runs against the SDK, whose Python packages pip treats as already
installed, but users run the application on the Platform runtime, which lacks
some of them. Run with:

    flatpak run --command=python3 --filesystem=<checkout> com.sharlychess.SharlyChess \
        <checkout>/scripts/export/linux/flatpak/scripts/check_runtime.py
"""

import importlib.metadata
import sys
from pathlib import Path

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


def missing_credentials_files() -> list[Path]:
    from database.sqlite.fide.fide_database import FideDatabase
    from plugins.chess_results.utils import CRUtils
    from plugins.ffe.ffe_database import FfeDatabase
    from plugins.ffe.ffe_sql_server import FFESqlServer
    from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase

    credentials_files = [
        FideDatabase.credentials_file(),
        CRUtils.CREDENTIALS_FILE,
        FFESqlServer.CREDENTIALS_FILE,
        FfeDatabase.credentials_file(),
        FRASchoolsDatabase.credentials_file(),
    ]
    return [file for file in credentials_files if not file.is_file()]


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

    missing = missing_credentials_files()
    if missing:
        print('Credentials files missing from the application:')
        for file in missing:
            print(f'  {file}')
        return 1

    print(
        'All requirements resolve, the application imports in the Platform runtime '
        'and its credentials files are present'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
