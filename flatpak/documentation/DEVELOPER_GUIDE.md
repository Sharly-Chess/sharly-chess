# 🛠️ Guide du Développeur Flatpak

Ce guide est destiné aux développeurs souhaitant maintenir, construire et tester le paquet Flatpak de Sharly Chess. Il couvre à la fois le développement local et l'intégration continue (CI/CD).

## 📋 Prérequis (Développement Local)

Pour construire et tester le paquet sur votre machine avant de pousser les changements.

### Configuration Système

- **Linux** : Ubuntu 20.04+, Debian 11+, Fedora 35+
- **RAM** : 4 GB minimum (8 GB recommandé)
- **Disque** : 5 GB d'espace libre
- **Internet** : Requis pour télécharger les dépendances

### Outils Requis

```bash
# Ubuntu/Debian
sudo apt-get install flatpak flatpak-builder python3-pip

# Fedora
sudo dnf install flatpak flatpak-builder python3-pip

# Vérification
flatpak --version
flatpak-builder --version
python3 --version
```

### Installation du Runtime

Flatpak a besoin du runtime GNOME 49 :

```bash
# Installer le runtime et le SDK GNOME 49
flatpak install flathub org.gnome.Platform//49
flatpak install flathub org.gnome.Sdk//49

# Vérifier l'installation
flatpak list --app
```

## 🚀 Build Local (Quick Start)

### 1. Cloner et Préparer

```bash
# Clone repository
git clone https://github.com/Sharly-Chess/sharly-chess.git
cd sharly-chess

# Ensure Flatpak directory exists
ls -la flatpak/

# Install Python dependencies for testing
pip3 install -r requirements-dev.txt
```

### 2. Run Quick Validation Tests

```bash
# Test only - no build
python3 flatpak/scripts/test_post_build.py

# Expected output:
# ✅ Manifest file exists
# ✅ Manifest is valid JSON
# ✅ Critical permissions
# ... etc
```

### 3. Full Build & Test

```bash
# 1. Construire le Flatpak (et l'installer en mode utilisateur)
flatpak-builder --force-clean --user --install build-dir flatpak/configuration/com.sharlychess.SharlyChess.json

# 2. Lancer l'application
flatpak run com.sharlychess.SharlyChess

# 3. Lancer les tests post-build
python3 flatpak/scripts/test_post_build.py
```

### 4. Résultat Attendu

```
# Pendant le build :
Downloading sources
Initializing build dir
...
Committing stage build-flatpak to cache

# Pendant l'exécution :
(La fenêtre de l'application doit s'ouvrir)
```
[Building... 5-15 minutes]
✅ Build successful

🧪 Running post-build tests...
============================================================
  FLATPAK POST-BUILD TEST SUITE
============================================================

1. Manifest Validation
✅ Manifest file exists
✅ Manifest is valid JSON
✅ Required fields present

2. Permissions & Configuration
✅ --share=network          → TCP binding + Internet
✅ --filesystem=home:rw     → Read/write filesystem
✅ Configuration files

3. Critical 3-Point Validation
✅ Point 1: TCP Network Binding
✅ Point 2: File Storage (R/W)
✅ Point 3: Internet Dependencies

4. Security Review
✅ Security: No hardcoded secrets

5. Environment
✅ Flatpak tools available

============================================================
  TEST SUMMARY
============================================================

Total Tests: 10
Passed:      10 ✅
Failed:      0 ❌
Success Rate: 100.0%

🟢 ALL TESTS PASSED - READY FOR PRODUCTION BUILD
```

## 🧪 Detailed Testing

### Test 1: Manifest Validation Only

```bash
python3 flatpak/scripts/test_post_build.py
```

Tests:
- ✅ Manifest file exists
- ✅ Valid JSON syntax
- ✅ Required fields present
- ✅ Critical permissions configured

### Test 2: Build Process

```bash
flatpak-builder --user --install --force-clean build-flatpak flatpak/configuration/com.sharlychess.SharlyChess.json
```

Output:
- Validates manifest
- Runs `flatpak-builder`
- Creates build-flatpak/repo/
- Generates build logs in .logs/

**Build Time**: 5-15 minutes (first build slower due to dependency downloads)

### Test 3: Post-Build Tests

```bash
python3 flatpak/scripts/test_post_build.py
```

Tests the 3 critical points:

1. **Point 1: TCP Network Binding**
   - Verifies `--share=network` permission
   - Service can bind to port 8000
   - External APIs accessible

2. **Point 2: File Storage (R/W)**
   - Verifies `--filesystem=home:rw` permission
   - Can create files in `~/.local/share/sharlychess/`
   - Database persistence works

3. **Point 3: Internet Dependencies**
   - Verifies `--share=network` permission
   - Can download Python packages via pip
   - Can fetch external sources (FFE, Chess-Results)

### Test 4: Security Review

```bash
python3 flatpak/scripts/test_post_build.py
```

Checks:
- ✅ No hardcoded API keys
- ✅ No hardcoded passwords
- ✅ No credentials in scripts
- ✅ Environment variables used instead

## 🧯 Troubleshooting

### Issue: "flatpak-builder: command not found"

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install flatpak-builder

# Fedora
sudo dnf install flatpak-builder
```

### Issue: "Runtime not installed"

**Solution**:
```bash
# Install required runtime
flatpak install flathub org.gnome.Platform//49
flatpak install flathub org.gnome.Sdk//49

# Verify
flatpak list --runtime
```

### Issue: Build fails with "Module not found"

**Solution**:
```bash
# Check Python version
python3 --version  # Should be 3.11+

# Verify manifest paths
cat flatpak/configuration/com.sharlychess.SharlyChess.json | grep -i "path"

# Check build logs
cat .logs/build-*.log | tail -50
```

### Issue: "Permission denied" errors

**Solution**:
```bash
# Check file permissions
ls -la flatpak/scripts/
chmod +x flatpak/scripts/*.py

# Run with sudo if needed (usually not required for user install)
flatpak-builder --user --install --force-clean build-flatpak flatpak/configuration/com.sharlychess.SharlyChess.json
```

### Issue: Build timeout

**Solution**:
```bash
# First build takes longer (15-20 minutes)
# Subsequent builds are faster (2-5 minutes)

# Try with verbose output to debug
flatpak-builder --user --install --force-clean --verbose build-flatpak flatpak/configuration/com.sharlychess.SharlyChess.json 2>&1 | tee build.log
```

## 📊 Build Logs

Build logs are saved in `.logs/` directory:

```bash
# View latest build log
tail -100 .logs/build-*.log

# Full log with grep
grep -E "ERROR|WARNING|FAILED" .logs/build-*.log

# Real-time monitoring
tail -f .logs/build-*.log
```

## 🧪 Manual Runtime Testing

After successful build, test the application manually:

### 1. Install Local Build

```bash
# Add local repository
flatpak remote-add --user --no-gpg-verify --if-not-exists \
    chess2-local "$(pwd)/build-flatpak/repo"

# List available
flatpak search --app chess2

# Install application
flatpak install --user chess2-local com.sharlychess.SharlyChess

# Or reinstall if already installed
flatpak update --user com.sharlychess.SharlyChess
```

### 2. Launch Application

```bash
# Run the application
flatpak run com.sharlychess.SharlyChess

# With debug output
flatpak run --env=SHARLY_DEBUG=1 com.sharlychess.SharlyChess

# In verbose mode
flatpak run --verbose com.sharlychess.SharlyChess
```

### 3. Test Critical Points

#### Point 1: Web Service (Port 8000)

```bash
# From another terminal
curl -I http://localhost:8000

# Expected: HTTP 200 or 307 (redirect)
```

#### Point 2: File Storage

```bash
# Check database created
ls -la ~/.local/share/sharlychess/

# Should contain:
# - sharlychess.db
# - tournaments/
# - players/
```

#### Point 3: Internet Access

```bash
# Check API connections
flatpak run com.sharlychess.SharlyChess --test-api

# Or in logs
journalctl --user-unit flatpak-com.sharlychess.SharlyChess.service
```

## 📦 Distribution

### For Local Testing

```bash
# Build only (no installation)
flatpak-builder --force-clean build-flatpak flatpak/configuration/com.sharlychess.SharlyChess.json

# Install locally
flatpak install --user --from flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml
```

### For Team Distribution

```bash
# Create distribution package (align with CI naming)
VERSION=$(python - <<'PY'
from pathlib import Path
import tomllib
data = tomllib.load(Path('pyproject.toml').open('rb'))
print(data['project']['version'])
PY
)
ARCH=$(uname -m)  # e.g. x86_64
flatpak build-bundle \
  build-flatpak/repo \
  com.sharlychess.SharlyChess-${VERSION}-${ARCH}.flatpak \
  com.sharlychess.SharlyChess \
  --arch=${ARCH}

# Share com.sharlychess.SharlyChess-${VERSION}-${ARCH}.flatpak
# Recipients install with:
flatpak install com.sharlychess.SharlyChess-${VERSION}-${ARCH}.flatpak
```

### For Flathub Submission

```bash
# See: docs/technical-appendices/flathub-submission.md
# Process requires PR to https://github.com/flathub/flathub
```

## 🔐 Security Notes

### Environment Variables

All sensitive data must use environment variables, NOT hardcoded:

```bash
# ✅ Correct
export CHESS_RESULTS_KEY="your-key"
export FFE_PASSWORD="your-password"

# ❌ WRONG - Don't do this!
# API_KEY="hardcoded-secret"
```

### Manifest Security

The test suite verifies:
- ✅ No credentials in manifest
- ✅ No API keys in scripts
- ✅ Proper permission scoping
- ✅ No world-readable secrets

## 📝 Intégration Continue (CI/CD)

Le build officiel est géré par GitHub Actions.

### Workflow
Le fichier de configuration est : `.github/workflows/publish-multiarch.yml`

### Déclenchement
Le build se lance automatiquement dans les cas suivants :
1.  **Tags** : Pousser un tag commençant par `v` (ex: `v3.4.3`).
2.  **Manuel** : Via l'onglet "Actions" de GitHub (bouton "Run workflow").

```bash
# Exemple de déclenchement par tag
git tag v3.4.3
git push origin v3.4.3
```

### Résultats
Le workflow effectue :
- ✅ Validation du manifest
- ✅ Build complet (Flatpak)
- ✅ Tests fonctionnels (15 tests)
- 📊 Génération de l'artefact `.flatpak` (téléchargeable depuis GitHub)

## 📞 Support

### Common Questions

**Q: How long does the build take?**
A: 5-15 minutes on first build, 2-5 minutes on subsequent builds.

**Q: Can I build on macOS/Windows?**
A: Only via Docker or virtual Linux machine.

**Q: Is the built Flatpak portable?**
A: Yes! It runs on any Linux with Flatpak installed.

**Q: Can I distribute the .flatpak file directly?**
A: Yes, for direct distribution. For Flathub, submit to their repository.

### Debugging

```bash
# Enable debug output
export SHARLY_DEBUG=1
flatpak-builder --user --install --force-clean --verbose build-flatpak flatpak/configuration/com.sharlychess.SharlyChess.json

# Check manifest
python3 -m json.tool flatpak/configuration/com.sharlychess.SharlyChess.json

# Verify permissions
grep -A 5 '"finish-args"' flatpak/configuration/com.sharlychess.SharlyChess.json

# Runtime logs
flatpak logs com.sharlychess.SharlyChess
```

## ✅ Checklist Before Submission

- [ ] All tests pass locally
- [ ] 3 critical points verified
- [ ] Security review passed
- [ ] Manual testing completed
- [ ] Build logs checked
- [ ] No hardcoded secrets
- [ ] README updated
- [ ] Version bumped

---

**Last Updated**: 2024
**Status**: Production Ready
