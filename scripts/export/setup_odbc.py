#!/usr/bin/env python3
"""
ODBC Setup for Exported Sharly Chess Applications

This script configures ODBC drivers when running the exported application.
It ensures that FreeTDS is properly configured for SQL Server connectivity.
"""

import os
import sys
from pathlib import Path
import tempfile


def setup_odbc_environment():
    """Set up ODBC environment for the exported application."""

    # Get the directory where the executable is running from
    if hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
    else:
        # Running as script
        bundle_dir = Path(__file__).parent

    # Only set up ODBC on non-Windows platforms
    if os.name == 'nt':
        return  # Windows should use built-in SQL Server driver

    # Check if we have a bundled ODBC configuration
    bundled_odbcinst = bundle_dir / 'etc' / 'odbcinst.ini'

    # Create temporary ODBC configuration
    temp_dir = Path(tempfile.gettempdir()) / 'sharly_chess_odbc'
    temp_dir.mkdir(exist_ok=True)

    odbcinst_ini = temp_dir / 'odbcinst.ini'

    # Check if FreeTDS libraries are available in the bundle
    freetds_lib = None
    for lib_name in ['libtdsodbc.so', 'libtdsodbc.0.so']:
        lib_path = bundle_dir / lib_name
        if lib_path.exists():
            freetds_lib = str(lib_path)
            break

    if freetds_lib:
        if bundled_odbcinst.exists():
            # Use bundled ODBC configuration but update library paths
            with open(bundled_odbcinst, 'r') as f:
                config_content = f.read()

            # Replace library paths with bundled paths
            config_content = config_content.replace(
                'Driver=/opt/homebrew/lib/libtdsodbc.so',
                f'Driver={freetds_lib}'
            ).replace(
                'Setup=/opt/homebrew/lib/libtdsodbc.so',
                f'Setup={freetds_lib}'
            ).replace(
                'Driver=/usr/local/lib/libtdsodbc.so',
                f'Driver={freetds_lib}'
            ).replace(
                'Setup=/usr/local/lib/libtdsodbc.so',
                f'Setup={freetds_lib}'
            )

            with open(odbcinst_ini, 'w') as f:
                f.write(config_content)
        else:
            # Create ODBC configuration for FreeTDS
            with open(odbcinst_ini, 'w') as f:
                f.write(f"""[FreeTDS]
Description=FreeTDS Driver for SQL Server
Driver={freetds_lib}
Setup={freetds_lib}
FileUsage=1
""")

        # Set environment variables for ODBC
        os.environ['ODBCSYSINI'] = str(temp_dir)
        os.environ['ODBCINSTINI'] = str(odbcinst_ini)
    else:
        print("Warning: FreeTDS libraries not found in bundle")


if __name__ == '__main__':
    setup_odbc_environment()
