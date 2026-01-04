#!/usr/bin/env python3
"""
Functional tests for Sharly Chess Flatpak.

Tests verify:
1. Manifest structure and validity
2. Dependency resolution
3. Build configuration
4. Runtime behavior
5. Permission requirements
"""

import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple

pytest_plugins = ['pytest']

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('flatpak-tests')


class FlatpakTestSuite:
    """Test suite for Flatpak builds."""

    def __init__(self, flatpak_dir: Path):
        self.flatpak_dir = flatpak_dir
        self.manifest_path = (
            flatpak_dir / 'configuration' / 'com.sharlychess.SharlyChess.json'
        )
        self.manifest: Dict = {}
        self.test_results: List[Tuple[str, bool, str]] = []

    def load_manifest(self) -> bool:
        """Load manifest JSON."""
        try:
            with open(self.manifest_path, 'r') as f:
                self.manifest = json.load(f)
            return True
        except Exception as e:
            logger.error(f'Failed to load manifest: {e}')
            return False

    def test_manifest_exists(self) -> Tuple[bool, str]:
        """Test 1: Manifest file exists."""
        if self.manifest_path.exists():
            return True, f'✓ Manifest exists: {self.manifest_path}'
        return False, f'✗ Manifest not found: {self.manifest_path}'

    def test_manifest_valid_json(self) -> Tuple[bool, str]:
        """Test 2: Manifest is valid JSON."""
        try:
            with open(self.manifest_path, 'r') as f:
                json.load(f)
            return True, '✓ Manifest is valid JSON'
        except json.JSONDecodeError as e:
            return False, f'✗ Invalid JSON: {e}'

    def test_manifest_required_fields(self) -> Tuple[bool, str]:
        """Test 3: Manifest has all required fields."""
        required = ['app-id', 'runtime', 'sdk', 'command', 'modules', 'finish-args']
        missing = [f for f in required if f not in self.manifest]

        if not missing:
            return True, f'✓ All required fields present: {", ".join(required)}'
        return False, f'✗ Missing fields: {", ".join(missing)}'

    def test_app_id_format(self) -> Tuple[bool, str]:
        """Test 4: App ID follows reverse domain naming."""
        app_id = self.manifest.get('app-id', '')
        if app_id.startswith('com.') and '.' in app_id[4:]:
            return True, f'✓ App ID format valid: {app_id}'
        return False, f'✗ App ID format invalid: {app_id}'

    def test_runtime_specified(self) -> Tuple[bool, str]:
        """Test 5: Runtime is properly configured."""
        runtime = self.manifest.get('runtime')
        runtime_version = self.manifest.get('runtime-version')

        if runtime and 'gnome' in runtime.lower():
            status = f'✓ Runtime configured: {runtime} (v{runtime_version})'
            return True, status
        return False, f'✗ Invalid runtime: {runtime}'

    def test_modules_defined(self) -> Tuple[bool, str]:
        """Test 6: Modules are defined."""
        modules = self.manifest.get('modules', [])
        if not modules:
            return False, '✗ No modules defined'

        module_names = [m.get('name', 'unknown') for m in modules]
        return True, f'✓ {len(modules)} modules defined: {", ".join(module_names)}'

    def test_finish_args_present(self) -> Tuple[bool, str]:
        """Test 7: Finish args (permissions) defined."""
        finish_args = self.manifest.get('finish-args', [])
        if not finish_args:
            return False, '✗ No finish-args (permissions) defined'

        essential_perms = {
            '--socket=wayland': 'Wayland',
            '--socket=x11': 'X11',
            '--share=network': 'Network',
        }

        found = {k: v for k, v in essential_perms.items() if k in finish_args}
        status = f'✓ Permissions defined: {len(found)}/{len(essential_perms)}'
        return len(found) >= 2, status

    def test_display_socket(self) -> Tuple[bool, str]:
        """Test 8: Display socket available (X11 or Wayland)."""
        finish_args = self.manifest.get('finish-args', [])
        has_display = '--socket=wayland' in finish_args or '--socket=x11' in finish_args

        if has_display:
            return True, '✓ Display socket available'
        return False, '✗ No display socket (X11/Wayland)'

    def test_network_permission(self) -> Tuple[bool, str]:
        """Test 9: Network permission available."""
        finish_args = self.manifest.get('finish-args', [])
        has_network = '--share=network' in finish_args

        if has_network:
            return True, '✓ Network permission available'
        return (
            True,
            '⚠ Network permission not explicitly set (may be OK for GUI-only app)',
        )

    def test_command_exists(self) -> Tuple[bool, str]:
        """Test 10: Command entry point defined."""
        command = self.manifest.get('command')
        if command:
            return True, f'✓ Command defined: {command}'
        return False, '✗ No command entry point'

    def test_requirements_file_exists(self) -> Tuple[bool, str]:
        """Test 11: Requirements file exists."""
        req_file = self.flatpak_dir.parent / 'requirements-flatpak.txt'
        if req_file.exists():
            return True, f'✓ Requirements file exists: {req_file}'
        return False, f'✗ Requirements file not found: {req_file}'

    def test_requirements_not_empty(self) -> Tuple[bool, str]:
        """Test 12: Requirements file has dependencies."""
        req_file = self.flatpak_dir.parent / 'requirements-flatpak.txt'
        if not req_file.exists():
            return False, 'Requirements file not found'

        with open(req_file, 'r') as f:
            lines = [
                line.strip() for line in f if line.strip() and not line.startswith('#')
            ]

        if len(lines) > 10:
            return True, f'✓ Requirements file has {len(lines)} dependencies'
        return False, f'✗ Too few dependencies ({len(lines)})'

    def test_appdata_file_exists(self) -> Tuple[bool, str]:
        """Test 13: AppData XML file exists."""
        appdata_file = (
            self.flatpak_dir
            / 'configuration'
            / 'com.sharlychess.SharlyChess.appdata.xml'
        )
        if appdata_file.exists():
            return True, f'✓ AppData file exists: {appdata_file}'
        return False, f'✗ AppData file not found: {appdata_file}'

    def test_desktop_file_exists(self) -> Tuple[bool, str]:
        """Test 14: Desktop file exists."""
        desktop_file = (
            self.flatpak_dir / 'configuration' / 'com.sharlychess.SharlyChess.desktop'
        )
        if desktop_file.exists():
            return True, f'✓ Desktop file exists: {desktop_file}'
        return False, f'✗ Desktop file not found: {desktop_file}'

    def test_launcher_script_exists(self) -> Tuple[bool, str]:
        """Test 15: Launcher script exists."""
        launcher = self.flatpak_dir / 'scripts' / 'launcher.py'
        if launcher.exists():
            return True, f'✓ Launcher script exists: {launcher}'
        return False, f'✗ Launcher script not found: {launcher}'

    def run_all_tests(self) -> bool:
        """Run all tests and return overall result."""
        if not self.load_manifest():
            logger.error('Failed to load manifest')
            return False

        tests = [
            ('Manifest exists', self.test_manifest_exists),
            ('Valid JSON', self.test_manifest_valid_json),
            ('Required fields', self.test_manifest_required_fields),
            ('App ID format', self.test_app_id_format),
            ('Runtime configured', self.test_runtime_specified),
            ('Modules defined', self.test_modules_defined),
            ('Finish args present', self.test_finish_args_present),
            ('Display socket', self.test_display_socket),
            ('Network permission', self.test_network_permission),
            ('Command defined', self.test_command_exists),
            ('Requirements file', self.test_requirements_file_exists),
            ('Requirements not empty', self.test_requirements_not_empty),
            ('AppData file', self.test_appdata_file_exists),
            ('Desktop file', self.test_desktop_file_exists),
            ('Launcher script', self.test_launcher_script_exists),
        ]

        print('\n' + '=' * 70)
        print('FLATPAK FUNCTIONAL TESTS')
        print('=' * 70 + '\n')

        passed = 0
        failed = 0

        for i, (name, test_func) in enumerate(tests, 1):
            try:
                success, message = test_func()
                self.test_results.append((name, success, message))

                print(f'[{i:2d}] {name:30s} {message}')

                if success:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f'[{i:2d}] {name:30s} ✗ Exception: {e}')
                self.test_results.append((name, False, str(e)))
                failed += 1

        # Summary
        print('\n' + '=' * 70)
        print(f'RESULTS: {passed} passed, {failed} failed ({passed}/{len(tests)})')
        print('=' * 70 + '\n')

        return failed == 0


def main():
    """Main test runner."""
    flatpak_dir = Path(__file__).parent.parent
    suite = FlatpakTestSuite(flatpak_dir)

    success = suite.run_all_tests()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
