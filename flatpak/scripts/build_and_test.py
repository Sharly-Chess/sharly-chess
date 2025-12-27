#!/usr/bin/env python3
"""
Flatpak Build & Test Automation

Automatise la construction et les tests post-build du Flatpak :
1. Valide le manifest
2. Lance la construction avec flatpak-builder
3. Exécute les tests post-build
4. Génère un rapport d'erreurs
5. Upload les logs si demandé

Usage:
    python flatpak/scripts/build_and_test.py [--skip-tests] [--verbose]
"""

import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List


class FlatpakBuildAndTest:
    """Build Flatpak and run tests."""
    
    def __init__(self, skip_tests=False, verbose=False):
        self.skip_tests = skip_tests
        self.verbose = verbose
        self.build_dir = Path("build-flatpak")
        self.repo_dir = self.build_dir / "repo"
        self.logs_dir = Path(".logs")
        self.start_time = None
        self.end_time = None
        
    def setup(self):
        """Setup build environment."""
        print("=" * 60)
        print("  FLATPAK BUILD & TEST AUTOMATION")
        print("=" * 60)
        print()
        
        self.start_time = time.time()
        self.logs_dir.mkdir(exist_ok=True)
        
        print(f"Build directory:   {self.build_dir}")
        print(f"Repository:        {self.repo_dir}")
        print(f"Logs directory:    {self.logs_dir}")
        print()
    
    def validate_manifest(self) -> bool:
        """Validate manifest JSON."""
        print("📋 Validating manifest...")
        
        manifest_path = Path("flatpak/configuration/com.sharlychess.SharlyChess.json")
        
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            
            # Check required fields
            required = ['app-id', 'runtime', 'sdk', 'command', 'finish-args', 'modules']
            missing = [f for f in required if f not in manifest]
            
            if missing:
                print(f"❌ Manifest is missing fields: {', '.join(missing)}")
                return False
            
            print("✅ Manifest is valid")
            return True
        
        except json.JSONDecodeError as e:
            print(f"❌ Manifest JSON error: {e}")
            return False
        except FileNotFoundError:
            print(f"❌ Manifest not found: {manifest_path}")
            return False
    
    def build_flatpak(self) -> bool:
        """Build Flatpak using flatpak-builder."""
        print("\n🔨 Building Flatpak...")
        
        # Check if flatpak-builder is available
        try:
            result = subprocess.run(
                ["flatpak-builder", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                print("❌ flatpak-builder not found")
                print("   Install: sudo apt install flatpak-builder")
                return False
        except FileNotFoundError:
            print("❌ flatpak-builder command not found")
            print("   Install: sudo apt install flatpak-builder")
            return False
        
        # Build command
        manifest = "flatpak/configuration/com.sharlychess.SharlyChess.json"
        
        cmd = [
            "flatpak-builder",
            "--repo=" + str(self.repo_dir),
            "--force-clean",
            str(self.build_dir),
            manifest
        ]
        
        if self.verbose:
            cmd.append("--verbose")
        
        print(f"\nCommand: {' '.join(cmd)}\n")
        
        # Log file
        log_file = self.logs_dir / f"build-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        
        try:
            with open(log_file, 'w') as log:
                result = subprocess.run(
                    cmd,
                    timeout=3600,  # 1 hour timeout
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            
            if result.returncode == 0:
                print("✅ Build successful")
                print(f"📝 Build log: {log_file}")
                return True
            else:
                print(f"❌ Build failed (exit code: {result.returncode})")
                print(f"📝 Build log: {log_file}")
                
                # Print last lines of log
                try:
                    with open(log_file) as f:
                        lines = f.readlines()
                        print("\n--- Last 20 lines of log ---")
                        for line in lines[-20:]:
                            print(line.rstrip())
                except:
                    pass
                
                return False
        
        except subprocess.TimeoutExpired:
            print("❌ Build timeout (1 hour exceeded)")
            return False
        except Exception as e:
            print(f"❌ Build error: {e}")
            return False
    
    def run_post_build_tests(self) -> bool:
        """Run post-build test suite."""
        print("\n🧪 Running post-build tests...")
        
        if self.skip_tests:
            print("⏭️  Tests skipped (--skip-tests)")
            return True
        
        # Import and run tests
        sys.path.insert(0, str(Path("flatpak/scripts")))
        
        try:
            from test_post_build import FlatpakPostBuildTester
            
            tester = FlatpakPostBuildTester()
            passed, failed = tester.run_all_tests()
            tester.print_summary()
            
            return failed == 0
        
        except ImportError as e:
            print(f"❌ Could not load test module: {e}")
            return False
        except Exception as e:
            print(f"❌ Test error: {e}")
            return False
    
    def generate_report(self, build_ok: bool, tests_ok: bool):
        """Generate final report."""
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        
        print("\n" + "=" * 60)
        print("  FINAL REPORT")
        print("=" * 60)
        print()
        
        print(f"Build Status:      {'✅ PASSED' if build_ok else '❌ FAILED'}")
        print(f"Tests Status:      {'✅ PASSED' if tests_ok else '❌ FAILED'}")
        print(f"Elapsed Time:      {elapsed:.1f}s")
        print()
        
        if build_ok and tests_ok:
            print("🟢 BUILD & TEST SUCCESSFUL - Ready for deployment")
            print()
            print("Next steps:")
            print("  1. Test on real machine:")
            print("     flatpak install repo com.sharlychess.SharlyChess")
            print("  2. Run the application:")
            print("     flatpak run com.sharlychess.SharlyChess")
            print("  3. Test critical functions:")
            print("     - Web service on port 8000")
            print("     - File persistence in ~/.local/share/")
            print("     - Network access (FFE, Chess-Results APIs)")
            return True
        else:
            print("🔴 BUILD OR TEST FAILED")
            print()
            if not build_ok:
                print("Build issues:")
                print(f"  - Check build log in {self.logs_dir}")
                print("  - Verify manifest syntax")
                print("  - Check permissions")
            if not tests_ok:
                print("Test issues:")
                print("  - Review test output above")
                print("  - Verify manifest configuration")
                print("  - Check permissions for 3 critical points")
            return False
    
    def run(self) -> int:
        """Run full build & test cycle."""
        self.setup()
        
        # Step 1: Validate
        if not self.validate_manifest():
            print("\n❌ Manifest validation failed")
            return 1
        
        # Step 2: Build
        if not self.build_flatpak():
            print("\n❌ Build failed")
            return 1
        
        # Step 3: Test
        if not self.run_post_build_tests():
            print("\n❌ Tests failed")
            return 1
        
        # Step 4: Report
        success = self.generate_report(build_ok=True, tests_ok=True)
        return 0 if success else 1


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build and test Flatpak package"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip post-build tests"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    builder = FlatpakBuildAndTest(
        skip_tests=args.skip_tests,
        verbose=args.verbose
    )
    
    sys.exit(builder.run())


if __name__ == "__main__":
    main()
