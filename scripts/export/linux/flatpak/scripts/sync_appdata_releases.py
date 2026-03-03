#!/usr/bin/env python3
"""Generate the <releases> section of the appdata XML from git annotated tags."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

FLATPAK_DIR = Path(__file__).resolve().parents[1]
APPDATA_FILE = FLATPAK_DIR / 'configuration' / 'com.sharlychess.SharlyChess.appdata.xml'

VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
VERSION_SUFFIX_RE = re.compile(r'\s*\((\d+[\.\d]*)\)\s*$')
MARKDOWN_ITALIC_RE = re.compile(r'_([^_]+)_')


def get_version_tags() -> list[str]:
    result = subprocess.run(
        ['git', 'tag', '--sort=-version:refname'],
        capture_output=True,
        text=True,
        check=True,
    )
    return [t for t in result.stdout.splitlines() if VERSION_RE.match(t)]


def is_annotated(tag: str) -> bool:
    result = subprocess.run(
        ['git', 'cat-file', '-t', tag],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == 'tag'


def get_tag_info(tag: str) -> tuple[str, str]:
    """Return (YYYY-MM-DD, message_body) for an annotated tag."""
    result = subprocess.run(
        ['git', 'cat-file', 'tag', tag],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = result.stdout

    # Parse tagger line for date
    date_str = ''
    for line in raw.splitlines():
        if line.startswith('tagger '):
            timestamp = int(line.split()[-2])
            date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
                '%Y-%m-%d'
            )
            break

    # Message body: after the first blank line, before PGP signature
    lines = raw.split('\n')
    i = 0
    while i < len(lines) and lines[i].strip():
        i += 1
    i += 1  # skip blank separator

    msg_lines: list[str] = []
    for line in lines[i:]:
        if line.startswith('-----BEGIN PGP SIGNATURE-----'):
            break
        msg_lines.append(line)

    while msg_lines and not msg_lines[-1].strip():
        msg_lines.pop()

    return date_str, '\n'.join(msg_lines)


def clean(text: str) -> str:
    """Strip Markdown italics, trailing version refs, and XML-escape."""
    text = MARKDOWN_ITALIC_RE.sub(r'\1', text)
    text = VERSION_SUFFIX_RE.sub('', text).strip()
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text


def bullet_version(text: str) -> str | None:
    """Return the version suffix of a bullet (e.g. '3.6.0'), or None if absent."""
    m = VERSION_SUFFIX_RE.search(text)
    return m.group(1) if m else None


def parse_message(message: str, version: str) -> list[tuple[str, list[str]]]:
    """
    Parse a tag message body into (header, bullets) sections.
    The first non-empty line (release summary) is skipped.
    Bullets are only included if they have no version suffix (native to this
    release) or if their version suffix matches `version`.
    Subsequent non-bullet lines start new sections.
    """
    sections: list[tuple[str, list[str]]] = []
    current_header = ''
    current_bullets: list[str] = []
    first_line = True

    for line in message.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('- '):
            body = stripped[2:].strip()
            bv = bullet_version(body)
            if bv is None or bv == version:
                current_bullets.append(clean(body))
        else:
            if first_line:
                first_line = False  # skip the release summary line
                continue
            sections.append((current_header, current_bullets))
            current_header = clean(stripped)
            current_bullets = []

    sections.append((current_header, current_bullets))
    return sections


def build_release_xml(version: str, date: str, message: str) -> str:
    sections = parse_message(message, version)
    lines = [f'    <release version="{version}" date="{date}">', '      <description>']
    for header, bullets in sections:
        if header:
            lines.append(f'        <p>{header}</p>')
        if bullets:
            lines.append('        <ul>')
            for bullet in bullets:
                lines.append(f'          <li>{bullet}</li>')
            lines.append('        </ul>')
    lines += ['      </description>', '    </release>']
    return '\n'.join(lines)


def update_appdata(releases_xml: str) -> None:
    content = APPDATA_FILE.read_text(encoding='utf-8')
    new_block = f'  <releases>\n{releases_xml}\n  </releases>'
    new_content, count = re.subn(
        r'  <releases>.*?</releases>', new_block, content, flags=re.DOTALL
    )
    if count == 0:
        raise RuntimeError('<releases> section not found in appdata file')
    APPDATA_FILE.write_text(new_content, encoding='utf-8')


def main() -> None:
    tags = get_version_tags()
    blocks: list[str] = []
    for tag in tags:
        if not is_annotated(tag):
            print(f'Skipping lightweight tag: {tag}')
            continue
        date, message = get_tag_info(tag)
        blocks.append(build_release_xml(tag, date, message))

    update_appdata('\n'.join(blocks))
    print(f'Updated {APPDATA_FILE} with {len(blocks)} releases.')


if __name__ == '__main__':
    main()
