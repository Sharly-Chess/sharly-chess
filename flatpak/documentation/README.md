# Sharly Chess - Flatpak Distribution

This directory contains all files and tools for building and distributing Sharly Chess as a Flatpak application on Linux.

## 🎯 Quick Start

### Prerequisites
```bash
# Install Flatpak tools
sudo apt-get install flatpak flatpak-builder

# Add Flathub
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# Install GNOME runtime
flatpak install flathub org.gnome.Platform//45 org.gnome.Sdk//45
```

### Build Locally (5-30 minutes)
```bash
cd sharly-chess/

# Validate configuration
python3 flatpak/scripts/validate.py

# Build application
flatpak-builder --user --install --force-clean build-flatpak \
  flatpak/configuration/com.sharlychess.SharlyChess.json

# Run application
flatpak run com.sharlychess.SharlyChess
```

### Run Tests
```bash
# Functional tests (15 tests)
python3 flatpak/testing/functional_tests.py

# Expected output: 15 passed, 0 failed
```

---

## 📁 Directory Structure

```
flatpak/
├── configuration/                  # Configuration & metadata files
│   ├── com.sharlychess.SharlyChess.json      # Main Flatpak manifest
│   ├── com.sharlychess.SharlyChess.appdata.xml # AppData for Flathub/Software Center
│   └── com.sharlychess.SharlyChess.desktop   # Desktop launcher
├── scripts/                        # Build & automation scripts
│   ├── launcher.py                # Application entrypoint for Flatpak
│   └── validate.py                # Manifest validation tool
├── testing/                        # Test suites
│   └── functional_tests.py        # 15 Flatpak-specific functional tests
├── ci-cd/                          # GitHub Actions workflows
│   └── flatpak-build.yml          # Automated build & test pipeline
├── documentation/                  # Guides & technical analysis
│   ├── 01-ANALYSE_REPOSITORY.md            # Sharly Chess architecture overview
│   ├── 02-ANALYSE_FLATPAK_FEASIBILITY.md   # Flatpak feasibility analysis
│   └── 03-MIGRATION_GUIDE.md               # Step-by-step migration guide
└── README.md                       # This file
```

---

## 🚀 Workflow

### 1. Local Development & Testing
```bash
# Validate manifest
python3 flatpak/scripts/validate.py

# Run functional tests (15 tests, takes ~1 second)
python3 flatpak/testing/functional_tests.py

# Build locally
flatpak-builder --user --install build-flatpak \
  flatpak/configuration/com.sharlychess.SharlyChess.json
```

### 2. CI/CD Automation (GitHub Actions)
Every push to `main` or PR triggers:
- ✓ Manifest validation
- ✓ Dependency checking
- ✓ Security checks
- ✓ AppData verification
- ✓ Build dry-run

### 3. Release to Flathub
```bash
# Create release branch
git checkout -b release/flatpak-3.4.3

# Update version in manifest, build & test
# Submit PR to Flathub repository
```

---

## 📋 Documentation Files

### Main Documentation
- **01-ANALYSE_REPOSITORY.md** - Repository architecture and code overview (40 KB)
- **02-ANALYSE_FLATPAK_FEASIBILITY.md** - Feasibility study and decision (60 KB)
- **03-MIGRATION_GUIDE.md** - Step-by-step implementation guide (50 KB)
- **04-FLATPAK_PERMISSIONS.md** - Permissions explanation and configuration ⭐ NEW
- **05-NETWORK_CONFIGURATION.md** - Web service networking (TCP ports, bind) ⭐ NEW
- **06-FILE_STORAGE.md** - Filesystem storage and persistence ⭐ NEW
- **INDEX.md** - Complete project index
- **README.md** - This file

### Key Security Documents (in ../../../)
- **GITHUB_SECRETS_CONFIGURATION.md** - Secret management guide
- **SECURITY_CREDENTIALS.md** - Credential security best practices
- **CI_CD_BUILD_INTEGRATION_SUMMARY.md** - CI/CD overview

---

## 🔐 Important: Permissions & Capabilities

Sharly Chess requires specific Flatpak permissions to function properly:

### Required Permissions
```json
{
  "finish-args": [
    "--socket=wayland",           // GUI display (modern)
    "--socket=x11",              // GUI display (compatible)
    "--socket=pulseaudio",       // Audio (notifications)
    "--share=network",           // Internet + TCP binding for web service
    "--filesystem=home:rw",      // Read/write access to home
    "--device=dri",              // GPU acceleration
    "--env=PYTHONUNBUFFERED=1",  // Python logging
    "--env=PYTHONPATH=/app/lib/python3.13/site-packages"
  ]
}
```

**⚠️ Important Details:**
1. **`--share=network`** enables Sharly Chess to:
   - Bind on TCP ports (8000, 8443, etc.)
   - Access external services (FFE database, Chess-Results API)
   - Download Python dependencies during build

2. **`--filesystem=home:rw`** enables Sharly Chess to:
   - Create/read/write databases (~/.local/share/sharly-chess/)
   - Store configuration (~/.config/sharly-chess/)
   - Generate reports and exports

3. **Internet Access** is required for:
   - Building (pip install packages in sandbox)
   - Runtime (connecting to external services)

See **04-FLATPAK_PERMISSIONS.md** for detailed explanation.

---

## 🌐 Network & Web Service Configuration

Sharly Chess is a web service that:
- Listens on TCP port 8000 (default)
- Serves HTTP/HTTPS traffic
- Connects to external databases (FFE)
- Integrates with Chess-Results API

**Configuration examples:**
```bash
# Default: localhost on 8000
flatpak run com.sharlychess.SharlyChess

# Custom port: 9000
flatpak run --env=SHARLY_CHESS_PORT=9000 com.sharlychess.SharlyChess

# Production: HTTPS + authentication
flatpak run --env=SHARLY_CHESS_SSL_ENABLED=1 com.sharlychess.SharlyChess
```

See **05-NETWORK_CONFIGURATION.md** for production setup and security.

---

## 💾 File Storage & Persistence

Sharly Chess stores data in standard XDG directories:

```
~/.local/share/sharly-chess/   # Application data (databases, logs, reports)
~/.config/sharly-chess/         # Configuration files
~/.cache/sharly-chess/          # Temporary cache
```

**Data persists across:**
- Application restarts
- Flatpak updates
- System reboots

**Backup recommendations:**
```bash
# Manual backup
tar -czf sharly-chess-backup.tar.gz \
  ~/.local/share/sharly-chess/ \
  ~/.config/sharly-chess/
```

See **06-FILE_STORAGE.md** for storage architecture and backup procedures.

---

## 📋 Configuration Files Explained

### 1. `com.sharlychess.SharlyChess.json`
The main Flatpak manifest. Contains:
- **Runtime**: `org.gnome.Platform//45` (GTK3/4, GLib, etc.)
- **SDK**: `org.gnome.Sdk//45` (build tools)
- **Python**: Installed via `org.gnome.Sdk.Extension.python313`
- **Modules**: 4 build modules (libffi, OpenSSL, Python deps, Sharly Chess)
- **Permissions**: Wayland, X11, Network, Home filesystem

### 2. `com.sharlychess.SharlyChess.appdata.xml`
Application metadata for:
- GNOME Software Center
- Flathub store
- Linux distribution apps
- Contains: description, screenshots, releases, links

### 3. `com.sharlychess.SharlyChess.desktop`
Desktop launcher file for:
- Application menus
- Desktop file integration
- Keyboard shortcuts

---

## 🔧 Available Tools

### Validation
```bash
# Validate manifest JSON & structure
python3 flatpak/scripts/validate.py

# Output: VALID or list of errors/warnings
```

### Testing
```bash
# Run comprehensive functional tests
python3 flatpak/testing/functional_tests.py

# Tests verify:
# - Manifest structure (15 checks)
# - Required fields
# - Permissions
# - Dependencies
# - Configuration files
```

### Launcher
```bash
# Located in flatpak/scripts/launcher.py
# Handles:
# - Environment setup for Flatpak sandbox
# - Dependency verification
# - Application initialization
```

---

## 🐛 Troubleshooting

### Build fails on cryptography
```bash
sudo apt-get install -y libffi-dev libssl-dev python3.13-dev
flatpak-builder --force-clean build-flatpak flatpak/configuration/...
```

### Permission denied errors
```bash
# Check permissions
flatpak info com.sharlychess.SharlyChess | grep Permissions

# Verify home directory access
ls -la ~/.local/share/sharly-chess/
```

### Port 9000 already in use
```bash
# Find process using port
lsof -i :9000

# Kill if needed or use different port
```

### More help
See [03-MIGRATION_GUIDE.md](documentation/03-MIGRATION_GUIDE.md) for detailed troubleshooting.

---

## 📊 Key Metrics

| Metric | Value |
|--------|-------|
| **Build Time** | 10-30 min (first build) |
| **Build Time** (cached) | 2-5 min |
| **App Size** | ~200-250 MB |
| **Runtime Size** | ~500 MB (shared, downloads once) |
| **Test Coverage** | 15 functional tests |
| **Supported Distributions** | 15+ (Ubuntu, Debian, Fedora, etc.) |

---

## ✅ Checklist for Release

- [ ] All 15 tests pass (`functional_tests.py`)
- [ ] Manifest validates (`validate.py`)
- [ ] CI/CD pipeline successful
- [ ] Tested on 3+ Linux distributions
- [ ] Version bumped in manifest (e.g., 3.4.3)
- [ ] AppData updated with new screenshots/descriptions
- [ ] Release notes prepared
- [ ] Documentation reviewed

---

## 📚 Further Reading

- [Flatpak Documentation](https://docs.flatpak.org/)
- [Flathub App Submission](https://github.com/flathub/flathub/wiki/App-Submission)
- [AppData Specification](https://www.freedesktop.org/software/appdata/docs/)
- [Sharly Chess Main Repository](https://github.com/sharly-chess/sharly-chess)

---

## 🤝 Contributing

To improve Flatpak support:
1. File an issue with the problem
2. Propose changes to files in `flatpak/`
3. Run tests: `python3 flatpak/testing/functional_tests.py`
4. Submit PR with explanation

---

## 📞 Support

- **Issues**: https://github.com/sharly-chess/sharly-chess/issues
- **Discord**: https://discord.gg/gE4Y7DVxdY
- **Email**: support@sharly-chess.com

---

**Maintained by**: Sharly Chess Development Team  
**Last Updated**: 2025-12-27  
**License**: AGPL v3.0
