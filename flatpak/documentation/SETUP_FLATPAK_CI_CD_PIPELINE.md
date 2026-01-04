# Configuration et Test du Build Flatpak CI/CD

Guide complet pour configurer et tester le build automatique avec les scripts d'initialisation sur https://github.com/Sharly-Chess/sharly-chess

## 📋 Contenu Livré

### 1. Workflow GitHub Actions
**Fichier**: `.github/workflows/build-test-with-init.yml`

Ce workflow automatique :
- Se déclenche à chaque push ou pull request
- Installe Python 3.13 et les dépendances
- Exécute les scripts d'initialisation Chess-Results et FFE
- Lance les tests
- Build l'application
- Conserve les artefacts pendant 7 jours

### 2. Scripts d'Initialisation
**Fichiers**:
- `scripts/chess_results/generate_chess_results_credentials.py`
- `scripts/ffe/generate_ffe_sql_server_credentials.py`

Ces scripts sont déjà présents dans le dépôt et sont utilisés par le workflow pour générer les fichiers de configuration nécessaires à partir des secrets.

## 🚀 Étapes de Mise en Place CI/CD

### Étape 1 : Vérifier les Fichiers

Assurez-vous que le workflow est présent :

```bash
ls .github/workflows/build-test-with-init.yml
```

### Étape 2 : Pousser le Code

```bash
git add .github/workflows/build-test-with-init.yml
git commit -m "feat: Add CI/CD with initialization scripts"
git push origin dev
```

### Étape 3 : Configurer les Secrets GitHub

**Option A : Via Interface Web**

1. Aller sur https://github.com/Sharly-Chess/sharly-chess/settings/secrets/actions
2. Cliquer "New repository secret" et créer 6 secrets :

| Name | Value |
|------|-------|
| `CHESS_RESULTS_ENCRYPTION_KEY` | `[REDACTED]` |
| `CHESS_RESULTS_ENCRYPTION_IV` | `[REDACTED]` |
| `FFE_SQL_SERVER_HOST` | `[REDACTED]` |
| `FFE_SQL_SERVER_USER` | `[REDACTED]` |
| `FFE_SQL_SERVER_PASSWORD` | `[REDACTED]` |
| `FFE_SQL_SERVER_DATABASE` | `[REDACTED]` |

**Option B : Via GitHub CLI (Recommandé)**

```bash
cd sharly-chess
gh auth login
gh secret set CHESS_RESULTS_ENCRYPTION_KEY --body "[REDACTED]"
gh secret set CHESS_RESULTS_ENCRYPTION_IV --body "[REDACTED]"
gh secret set FFE_SQL_SERVER_HOST --body "[REDACTED]"
gh secret set FFE_SQL_SERVER_USER --body "[REDACTED]"
gh secret set FFE_SQL_SERVER_PASSWORD --body "[REDACTED]"
gh secret set FFE_SQL_SERVER_DATABASE --body "[REDACTED]"

# Vérifier
gh secret list
```

### Étape 4 : Tester le Workflow

**Déclencher manuellement**:

1. Aller sur https://github.com/Sharly-Chess/sharly-chess/actions
2. Sélectionner "Build with Initialization Scripts"
3. Cliquer "Run workflow" → "Run workflow"
4. Observer l'exécution

**Ou via CLI**:

```bash
gh workflow run build-test-with-init.yml --ref main
gh run list
gh run view <run-id> --log
```

## 📊 Flux d'Exécution Détaillé

```
┌─────────────────────────────────┐
│ Push vers GitHub (main/develop) │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Déclenchement du workflow       │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Checkout du code                │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Setup Python 3.13 + cache pip   │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Install dependencies            │
│ (pip install -r requirements)   │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────────────────────────┐
│ Run Chess-Results Init (avec secrets)               │
│ $ python scripts/chess_results/generate_...py \    │
│   --key=${CHESS_RESULTS_ENCRYPTION_KEY} \          │
│   --iv=${CHESS_RESULTS_ENCRYPTION_IV}              │
└────────────┬────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────┐
│ Run FFE Init (avec secrets + --github flag)         │
│ $ python scripts/ffe/generate_ffe_sql_server...py \ │
│   --host=${FFE_SQL_SERVER_HOST} \                  │
│   --user=${FFE_SQL_SERVER_USER} \                  │
│   --password=${FFE_SQL_SERVER_PASSWORD} \          │
│   --database=${FFE_SQL_SERVER_DATABASE} --github   │
└────────────┬────────────────────────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Exécuter tests                  │
│ pytest tests/ -v                │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Build avec PyInstaller          │
│ pyinstaller --onefile src/...   │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Upload des artefacts (7 jours)  │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ ✅ Build Completed              │
└─────────────────────────────────┘
```

## 🔒 Gestion des Secrets

### Points de Sécurité

✅ **Chiffré**: Les secrets sont chiffrés par GitHub au repos
✅ **Masqué**: Les valeurs ne s'affichent jamais dans les logs
✅ **Isolé**: Accessibles uniquement par le workflow autorisé
✅ **Audité**: Traces d'accès dans les logs GitHub

### Les secrets ne sontPAS visibles en clair

```bash
# ❌ Ceci ne fonctionne pas
echo $CHESS_RESULTS_ENCRYPTION_KEY  # Vide en dehors du workflow

# ✅ Accessible dans le workflow
run: echo $CHESS_RESULTS_ENCRYPTION_KEY  # *** (masqué dans les logs)
```

## 🧪 Tests Locaux (Sans GitHub)

### Avant de configurer les secrets, tester localement :

```bash
# Mode développement local
python init-credentials.py \
  --chess-results-key=[REDACTED] \
  --chess-results-iv=[REDACTED] \
  --ffe-host=[REDACTED] \
  --ffe-user=[REDACTED] \
  --ffe-password=[REDACTED] \
  --ffe-database=[REDACTED]

# Ou via variables d'environnement
export CHESS_RESULTS_ENCRYPTION_KEY=[REDACTED]
export CHESS_RESULTS_ENCRYPTION_IV=[REDACTED]
export FFE_SQL_SERVER_HOST=[REDACTED]
export FFE_SQL_SERVER_USER=[REDACTED]
export FFE_SQL_SERVER_PASSWORD=[REDACTED]
export FFE_SQL_SERVER_DATABASE=[REDACTED]

python init-credentials.py --github
```

## 📈 Monitoring du Build

### Accéder aux Logs

1. **Via GitHub Web**:
   - Actions tab → "Build with Initialization Scripts" → dernière exécution
   - Cliquer sur "Logs" pour voir chaque étape

2. **Via GitHub CLI**:
   ```bash
   gh run list                    # Lister les runs
   gh run view <run-id>          # Voir le statut
   gh run view <run-id> --log    # Télécharger les logs complets
   ```

### Récupérer les Artefacts

```bash
# Lister les artefacts
gh run view <run-id> --json artifacts

# Télécharger
gh run download <run-id> -n build-artifacts
```

## 🆘 Dépannage

### Le workflow s'exécute mais les scripts ne tournent pas

**Cause**: Secrets non configurés
**Solution**: Vérifier la configuration des secrets
```bash
gh secret list
```

### Erreur "command not found: python"

**Cause**: Python pas dans le PATH
**Solution**: Workflow utilise `python3`
```yaml
run: python3 init-credentials.py --github
```

### Le build échoue après initialisation

**Causes possibles**:
1. Crédentiels FFE invalides
2. Base de données FFE non accessible (normal en GitHub)
3. Dépendances Python manquantes

**Solution**: Consulter les logs détaillés du workflow

### Comment relancer un workflow ?

```bash
gh workflow run build-test-with-init.yml --ref main
```

## 📚 Fichiers de Référence

| Fichier | Destination | Description |
|---------|-------------|-------------|
| `build-test-with-init.yml` | `.github/workflows/` | Workflow GitHub Actions |
| `init-credentials.py` | Racine du projet | Script d'initialisation dual-mode |

## ✅ Checklist de Mise en Place

- [ ] Copier `.github/workflows/build-test-with-init.yml`
- [ ] Copier `init-credentials.py`
- [ ] Commit et push vers sharly-chess
- [ ] Configurer 6 secrets GitHub
- [ ] Vérifier la configuration avec `gh secret list`
- [ ] Déclencher un test manuel du workflow
- [ ] Vérifier les logs de succès
- [ ] Récupérer l'exécutable dans les artefacts

## 🎯 Prochaines Étapes

1. **Build multi-plateforme**: Ajouter Linux/macOS à la matrice
2. **Packaging Flatpak**: Utiliser le workflow pour build Flatpak
3. **Releases automatiques**: Créer une release à chaque tag
4. **Distribution**: Publier sur Flathub, Microsoft Store, etc.
5. **Notifications**: Ajouter Slack/Discord pour les alertes

## 📞 Support

- Documentation générale: `docs/technical-appendices/`
- Workflow: Voir `.github/workflows/build-test-with-init.yml`
- Scripts: Voir `init-credentials.py`
