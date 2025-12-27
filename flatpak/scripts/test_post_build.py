#!/usr/bin/env python3
"""
Post-Build Flatpak Test Suite

Tests locaux à exécuter après construction du package Flatpak :
1. Valide le manifest
2. Teste les permissions critiques  
3. Teste la structure des fichiers
4. Vérifie les 3 points essentiels
5. Test de lancement (si possible)

Usage:
    python flatpak/scripts/test_post_build.py
"""

import subprocess
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple


class FlatpakPostBuildTester:
    """Post-build test suite for Flatpak package."""
    
    def __init__(self):
        self.test_results: Dict[str, bool] = {}
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        
    def print_header(self, title: str):
        """Print test section header."""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")
    
    def print_test(self, name: str, passed: bool, details: str = ""):
        """Print test result."""
        status = "✅" if passed else "❌"
        print(f"{status} {name}")
        if details:
            print(f"   {details}")
        
        self.test_count += 1
        if passed:
            self.passed_count += 1
        else:
            self.failed_count += 1
    
    def test_manifest_exists(self) -> bool:
        """Test 1: Manifest file exists."""
        manifest_path = Path("flatpak/configuration/com.sharlychess.SharlyChess.json")
        exists = manifest_path.exists()
        self.print_test(
            "Manifest file exists",
            exists,
            f"Path: {manifest_path}"
        )
        return exists
    
    def test_manifest_valid_json(self) -> bool:
        """Test 2: Manifest is valid JSON."""
        try:
            with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
                json.load(f)
            self.print_test("Manifest is valid JSON", True)
            return True
        except json.JSONDecodeError as e:
            self.print_test("Manifest is valid JSON", False, str(e))
            return False
    
    def test_required_fields(self) -> bool:
        """Test 3: Manifest has all required fields."""
        with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
            manifest = json.load(f)
        
        required = ['app-id', 'runtime', 'sdk', 'command', 'finish-args', 'modules']
        missing = [f for f in required if f not in manifest]
        
        if missing:
            self.print_test(
                "Required fields present",
                False,
                f"Missing: {', '.join(missing)}"
            )
            return False
        
        self.print_test("Required fields present", True)
        return True
    
    def test_critical_permissions(self) -> bool:
        """Test 4: Critical permissions configured."""
        with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
            manifest = json.load(f)
        
        args = manifest.get('finish-args', [])
        critical_perms = {
            '--share=network': 'TCP binding + Internet',
            '--filesystem=home:rw': 'Read/write filesystem',
            '--socket=wayland': 'Wayland GUI',
            '--socket=x11': 'X11 compatibility'
        }
        
        all_present = True
        for perm, desc in critical_perms.items():
            if perm in args:
                print(f"  ✅ {perm:25} → {desc}")
            else:
                print(f"  ❌ {perm:25} → {desc}")
                all_present = False
        
        self.print_test("Critical permissions", all_present)
        return all_present
    
    def test_point_1_tcp_binding(self) -> bool:
        """Test 5: Point 1 - TCP Binding Network."""
        with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
            manifest = json.load(f)
        
        has_network = '--share=network' in manifest.get('finish-args', [])
        
        details = "Service can bind to port 8000" if has_network else "Missing --share=network"
        self.print_test(
            "Point 1: TCP Network Binding",
            has_network,
            details
        )
        return has_network
    
    def test_point_2_file_storage(self) -> bool:
        """Test 6: Point 2 - File Storage Read/Write."""
        with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
            manifest = json.load(f)
        
        has_rw = '--filesystem=home:rw' in manifest.get('finish-args', [])
        
        details = "Can create & modify files in ~/.local/share/" if has_rw else "Missing --filesystem=home:rw"
        self.print_test(
            "Point 2: File Storage (R/W)",
            has_rw,
            details
        )
        return has_rw
    
    def test_point_3_internet_deps(self) -> bool:
        """Test 7: Point 3 - Internet Dependencies."""
        with open("flatpak/configuration/com.sharlychess.SharlyChess.json") as f:
            manifest = json.load(f)
        
        # Network permission needed
        has_network = '--share=network' in manifest.get('finish-args', [])
        
        # Check for external sources
        modules = manifest.get('modules', [])
        has_external_sources = False
        
        for module in modules:
            sources = module.get('sources', [])
            for source in sources:
                if source.get('type') == 'archive':
                    url = source.get('url', '')
                    if 'http' in url:
                        has_external_sources = True
                        break
        
        valid = has_network and has_external_sources
        details = "Can download pip packages & external sources" if valid else "Missing internet permission or sources"
        
        self.print_test(
            "Point 3: Internet Dependencies",
            valid,
            details
        )
        return valid
    
    def test_configuration_files(self) -> bool:
        """Test 8: Configuration files exist."""
        files_to_check = [
            "flatpak/configuration/com.sharlychess.SharlyChess.desktop",
            "flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml"
        ]
        
        all_exist = True
        for file_path in files_to_check:
            if Path(file_path).exists():
                print(f"  ✅ {file_path}")
            else:
                print(f"  ❌ {file_path}")
                all_exist = False
        
        self.print_test("Configuration files", all_exist)
        return all_exist
    
    def test_security_no_secrets(self) -> bool:
        """Test 9: No hardcoded secrets in files."""
        dangerous_files = [
            "flatpak/scripts/launcher.py",
            "flatpak/scripts/validate.py",
            "init-credentials.py"
        ]
        
        # Patterns to search for
        secret_patterns = [
            "[REDACTED_KEY]",  # FFE key pattern
            "[REDACTED_IV]",   # FFE IV pattern
            "[REDACTED_PWD]",  # FFE password pattern
            "[REDACTED_USER]"  # FFE user pattern
        ]
        
        found_secrets = False
        for file_path in dangerous_files:
            if not Path(file_path).exists():
                continue
            
            with open(file_path) as f:
                content = f.read()
                for pattern in secret_patterns:
                    if pattern in content:
                        print(f"  ❌ Found secret in {file_path}: {pattern}")
                        found_secrets = True
        
        if not found_secrets:
            print("  ✅ No hardcoded secrets detected")
        
        self.print_test("Security: No hardcoded secrets", not found_secrets)
        return not found_secrets
    
    def test_flatpak_info_available(self) -> bool:
        """Test 10: Flatpak info command works."""
        try:
            result = subprocess.run(
                ["flatpak", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            available = result.returncode == 0
            version = result.stdout.strip() if available else "Not installed"
            
            self.print_test(
                "Flatpak tools available",
                available,
                version
            )
            return available
        except FileNotFoundError:
            self.print_test(
                "Flatpak tools available",
                False,
                "flatpak command not found"
            )
            return False
    
    def run_all_tests(self) -> Tuple[int, int]:
        """Run all tests and return pass/fail counts."""
        self.print_header("FLATPAK POST-BUILD TEST SUITE")
        
        # Manifest tests
        self.print_header("1. Manifest Validation")
        self.test_manifest_exists()
        self.test_manifest_valid_json()
        self.test_required_fields()
        
        # Permissions tests
        self.print_header("2. Permissions & Configuration")
        self.test_critical_permissions()
        self.test_configuration_files()
        
        # 3 Essential Points
        self.print_header("3. Critical 3-Point Validation")
        self.test_point_1_tcp_binding()
        self.test_point_2_file_storage()
        self.test_point_3_internet_deps()
        
        # Security tests
        self.print_header("4. Security Review")
        self.test_security_no_secrets()
        
        # Environment tests
        self.print_header("5. Environment")
        self.test_flatpak_info_available()
        
        return self.passed_count, self.failed_count
    
    def print_summary(self):
        """Print test summary."""
        self.print_header("TEST SUMMARY")
        
        total = self.passed_count + self.failed_count
        percentage = (self.passed_count / total * 100) if total > 0 else 0
        
        print(f"Total Tests: {total}")
        print(f"Passed:      {self.passed_count} ✅")
        print(f"Failed:      {self.failed_count} ❌")
        print(f"Success Rate: {percentage:.1f}%")
        print()
        
        if self.failed_count == 0:
            print("🟢 ALL TESTS PASSED - READY FOR PRODUCTION BUILD")
            return True
        else:
            print("🔴 SOME TESTS FAILED - REVIEW REQUIRED")
            return False


def main():
    """Run the test suite."""
    tester = FlatpakPostBuildTester()
    passed, failed = tester.run_all_tests()
    tester.print_summary()
    
    # Exit with error code if any test failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
