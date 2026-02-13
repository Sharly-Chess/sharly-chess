#!/usr/bin/env python3
"""
Flatpak build and validation script.

This script handles:
1. Manifest JSON validation
2. Dependency resolution
3. Build configuration
4. Pre-build checks
"""

import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('flatpak-builder')


class FlatpakManifestValidator:
    """Validates Flatpak manifest JSON files."""

    REQUIRED_FIELDS = ['app-id', 'runtime', 'sdk', 'command', 'modules', 'finish-args']

    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.manifest: Dict = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_manifest(self) -> bool:
        """Load and parse manifest JSON."""
        if not self.manifest_path.exists():
            self.errors.append(f'Manifest not found: {self.manifest_path}')
            return False

        try:
            with open(self.manifest_path, 'r') as f:
                self.manifest = json.load(f)
            logger.info(f'Loaded manifest: {self.manifest_path}')
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f'Invalid JSON: {e}')
            return False
        except Exception as e:
            self.errors.append(f'Failed to load manifest: {e}')
            return False

    def validate_structure(self) -> bool:
        """Validate manifest structure."""
        logger.info('Validating manifest structure...')

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in self.manifest:
                self.errors.append(f'Missing required field: {field}')

        # Validate app-id format
        app_id = self.manifest.get('app-id', '')
        if not app_id.startswith('com.'):
            self.warnings.append(f'App ID should start with "com.": {app_id}')

        # Validate runtime version
        runtime = self.manifest.get('runtime', '')
        if not runtime:
            self.errors.append('Runtime not specified')

        # Validate modules
        modules = self.manifest.get('modules', [])
        if not modules:
            self.errors.append('No modules defined')
        else:
            for i, module in enumerate(modules):
                if 'name' not in module:
                    self.errors.append(f'Module {i} missing "name" field')

        return len(self.errors) == 0

    def validate_dependencies(self) -> bool:
        """Validate module dependencies."""
        logger.info('Validating dependencies...')

        modules = self.manifest.get('modules', [])
        module_names = {m.get('name'): m for m in modules}

        for module_name, module in module_names.items():
            module_deps = module.get('modules', [])
            for dep in module_deps:
                dep_name = dep.get('name') if isinstance(dep, dict) else dep
                if dep_name and dep_name not in module_names:
                    self.warnings.append(
                        f'Module "{module_name}" depends on unknown module "{dep_name}"'
                    )

        return True

    def validate_permissions(self) -> bool:
        """Validate finish-args permissions."""
        logger.info('Validating permissions...')

        finish_args = self.manifest.get('finish-args', [])

        # Check for essential permissions
        # essential_perms = {
        #     '--socket=wayland': 'Wayland socket (modern display)',
        #     '--socket=x11': 'X11 socket (legacy display)',
        #     '--share=network': 'Network access',
        # }

        found_display = any(
            arg in finish_args for arg in ['--socket=wayland', '--socket=x11']
        )
        if not found_display:
            self.warnings.append(
                'No display socket specified (--socket=wayland or --socket=x11)'
            )

        found_network = '--share=network' in finish_args
        if not found_network:
            self.warnings.append('Network access not enabled (--share=network)')

        return True

    def generate_report(self) -> Tuple[bool, str]:
        """Generate validation report."""
        report = []
        report.append('\n' + '=' * 60)
        report.append('FLATPAK MANIFEST VALIDATION REPORT')
        report.append('=' * 60)

        # Manifest info
        report.append(f'\nManifest: {self.manifest_path}')
        report.append(f'App ID: {self.manifest.get("app-id", "N/A")}')
        report.append(f'Runtime: {self.manifest.get("runtime", "N/A")}')
        report.append(f'Modules: {len(self.manifest.get("modules", []))}')

        # Errors
        if self.errors:
            report.append(f'\n❌ ERRORS ({len(self.errors)}):')
            for error in self.errors:
                report.append(f'  - {error}')

        # Warnings
        if self.warnings:
            report.append(f'\n⚠️  WARNINGS ({len(self.warnings)}):')
            for warning in self.warnings:
                report.append(f'  - {warning}')

        # Result
        status = '✓ VALID' if not self.errors else '✗ INVALID'
        report.append(f'\n{status}')
        report.append('=' * 60 + '\n')

        return not bool(self.errors), '\n'.join(report)

    def validate(self) -> Tuple[bool, str]:
        """Run full validation."""
        if not self.load_manifest():
            return False, '\n'.join(self.errors)

        self.validate_structure()
        self.validate_dependencies()
        self.validate_permissions()

        return self.generate_report()


def validate_requirements_file(req_path: Path) -> Tuple[bool, List[str]]:
    """Validate requirements-flatpak.txt file."""
    logger.info(f'Validating requirements: {req_path}')

    issues = []

    if not req_path.exists():
        issues.append(f'Requirements file not found: {req_path}')
        return False, issues

    try:
        with open(req_path, 'r') as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Basic validation
            if '==' in line and '>=' in line:
                issues.append(f'Line {i}: Invalid version specifier: {line}')

        if not issues:
            logger.info(
                f'Requirements file valid ({len([line for line in lines if line.strip() and not line.strip().startswith("#")])} packages)'
            )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f'Failed to read requirements file: {e}')
        return False, issues


def main():
    """Main validation script."""
    logger.info('Starting Flatpak validation...')

    # Paths
    flatpak_dir = Path(__file__).parent.parent
    manifest_path = flatpak_dir / 'configuration' / 'com.sharlychess.SharlyChess.json'
    requirements_path = flatpak_dir.parent / 'requirements-flatpak.txt'

    # Validate manifest
    validator = FlatpakManifestValidator(manifest_path)
    manifest_ok, manifest_report = validator.validate()
    print(manifest_report)

    # Validate requirements
    req_ok, req_issues = validate_requirements_file(requirements_path)
    if req_issues:
        print(f'\n❌ Requirements file issues ({len(req_issues)}):')
        for issue in req_issues:
            print(f'  - {issue}')
    else:
        print('\n✓ Requirements file valid')

    # Overall result
    success = manifest_ok and req_ok
    if success:
        logger.info('✓ All validations passed!')
        return 0
    else:
        logger.error('✗ Validation failed')
        return 1


if __name__ == '__main__':
    sys.exit(main())
