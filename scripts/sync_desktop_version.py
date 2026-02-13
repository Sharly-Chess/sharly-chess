#!/usr/bin/env python3
"""Sync the .desktop file Version field with project version from pyproject.toml."""

from __future__ import annotations

import re
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / 'pyproject.toml'
DESKTOP_FILE = (
    ROOT / 'flatpak' / 'configuration' / 'com.sharlychess.SharlyChess.desktop'
)


def load_version_from_pyproject() -> str:
    with PYPROJECT.open('rb') as f:
        data = tomllib.load(f)
    return data['project']['version']


def update_desktop(version: str) -> None:
    content = DESKTOP_FILE.read_text(encoding='utf-8')
    new_content, count = re.subn(
        r'^Version=.*$', f'Version={version}', content, flags=re.MULTILINE
    )
    if count == 0:
        raise RuntimeError('Version field not found in desktop file')
    DESKTOP_FILE.write_text(new_content, encoding='utf-8')


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description='Sync .desktop Version with provided value or pyproject.toml'
    )
    parser.add_argument(
        '--version',
        dest='version',
        help='Version string to set (overrides pyproject.toml)',
    )
    args = parser.parse_args()

    version = args.version or load_version_from_pyproject()
    update_desktop(version)


if __name__ == '__main__':
    main()
