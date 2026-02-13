# Guide Développeur — Flatpak CI/CD

Ce document est destiné aux **développeurs** qui contribuent au projet. Il explique l'architecture CI/CD, les workflows automatisés, et les procédures à suivre. **Aucun build local n'est nécessaire** — tout passe par GitHub Actions.

---

## Architecture générale

Le fork `GillesHorn/sharly-chess` sert de distribution Linux Flatpak de l'application upstream `Sharly-Chess/sharly-chess`.

```
┌────────────────────────────────┐
│  Upstream (Sharly-Chess)       │
│  Releases : stable + beta      │
└───────────┬────────────────────┘
            │ sync (auto ou manuel)
            ▼
┌────────────────────────────────┐
│  Fork (GillesHorn)             │
│  Branche : linux-flatpak       │
│                                │
│  ┌──────────────────────┐      │
│  │ publish-multiarch.yml│      │
│  │ (build + publish)    │      │
│  └──────┬───────┬───────┘      │
│         │       │              │
│    ┌────▼──┐ ┌──▼─────┐       │
│    │repo/  │ │repo-dev/│       │
│    │(prod) │ │(dev)    │       │
│    └───────┘ └─────────┘       │
│                                │
│    GitHub Pages (gh-pages)     │
└────────────────────────────────┘
```

### Branches

| Branche | Rôle |
|---------|------|
| `linux-flatpak` | Branche principale du fork. Contient le code + la configuration Flatpak |
| `dev` | Synced avec upstream (non utilisée directement) |
| `gh-pages` | Héberge les dépôts OSTree (`repo/` et `repo-dev/`) via GitHub Pages |

### Dépôts OSTree (GitHub Pages)

| Dépôt | Contenu | URL |
|-------|---------|-----|
| `repo/` | Versions stables uniquement | `https://gilleshorn.github.io/sharly-chess/repo/` |
| `repo-dev/` | Chaque push sur `linux-flatpak` | `https://gilleshorn.github.io/sharly-chess/repo-dev/` |

---

## Workflows GitHub Actions

### 1. `publish-multiarch.yml` — Build & Publish

C'est le workflow principal. Il construit le Flatpak en multi-architecture et publie sur GitHub Pages.

```
                        ┌─────────────────┐
                        │    Déclencheur   │
                        │                  │
                        │ • push tag → prod│
                        │ • push branch →  │
                        │   dev            │
                        │ • manual dispatch│
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            ┌───────────────┐         ┌───────────────┐
            │  build-x86    │         │  build-arm64  │
            │  (ubuntu-24)  │         │  (ubuntu-24   │
            │               │         │   ARM runner) │
            │ 1. Checkout   │         │               │
            │ 2. Runtimes   │         │  (mêmes       │
            │ 3. Secrets    │         │   étapes)     │
            │ 4. Build      │         │               │
            │ 5. Bundle     │         │               │
            │ 6. Archive    │         │               │
            │    OSTree     │         │               │
            └───────┬───────┘         └───────┬───────┘
                    │                         │
                    └────────────┬────────────┘
                                 │ artifacts
                                 ▼
                    ┌─────────────────────────┐
                    │        publish          │
                    │                          │
                    │ 1. Checkout gh-pages     │
                    │ 2. Download artifacts    │
                    │ 3. Cible: repo/ ou       │
                    │    repo-dev/             │
                    │ 4. Import GPG            │
                    │ 5. Merge repos OSTree    │
                    │ 6. Signer commits        │
                    │ 7. Static deltas         │
                    │    (+ from-empty)        │
                    │ 8. Générer .flatpakrepo  │
                    │ 9. Push gh-pages         │
                    └─────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │    notify-failure       │
                    │   (si échec → Issue)    │
                    └─────────────────────────┘
```

#### Déclencheurs

| Événement | Cible | Exemple |
|-----------|-------|---------|
| Push tag `*` | **Production** (`repo/`) | Tag `3.5.2` → build + publish stable |
| Push branche `linux-flatpak` | **Dev** (`repo-dev/`) | Commit → build + publish dev |
| Manual dispatch avec `version_tag` | **Production** (`repo/`) | Rebuild d'un tag existant |
| Manual dispatch sans `version_tag` | **Dev** (`repo-dev/`) | Build dev à la demande |

> **Note :** Les modifications des fichiers `*.md`, `docs/**` et `flatpak/documentation/**` ne déclenchent **pas** de build (cf. `paths-ignore`).

#### Secrets GitHub requis

| Secret | Description |
|--------|-------------|
| `GPG_PRIVATE_KEY` | Clé GPG privée pour signer le dépôt OSTree |
| `FFE_HOSTNAME` | Hôte du serveur SQL FFE |
| `FFE_USER` | Utilisateur SQL FFE |
| `FFE_PASSWORD` | Mot de passe SQL FFE |
| `FFE_DATABASE` | Nom de la base FFE |
| `CHESS_RESULTS_AES_KEY` | Clé AES Chess-Results |
| `CHESS_RESULTS_AES_IV` | IV AES Chess-Results |

#### Optimisations

- **Static deltas** : Générés automatiquement par `flatpak build-update-repo --generate-static-deltas` pour les mises à jour incrémentales.
- **Static deltas from-empty** : Générés par `ostree static-delta generate --empty` pour accélérer la première installation (évite des milliers de petites requêtes HTTP).
- **Prune** : `--prune` supprime les objets OSTree obsolètes pour limiter la taille du dépôt.
- **Historique préservé** : `flatpak build-commit-from` relie chaque nouveau commit au précédent, permettant le rollback et les delta updates.

---

### 2. `sync-upstream.yml` — Synchronisation upstream

Ce workflow détecte et intègre automatiquement les nouvelles releases upstream.

```
                ┌─────────────────────┐
                │     Déclencheur     │
                │                     │
                │ • cron: toutes les  │
                │   6 heures          │
                │ • manual dispatch   │
                │   (tag spécifique)  │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Détection release   │
                │                     │
                │ API GitHub Releases │
                │ (5 dernières)       │
                │                     │
                │ Cherche la première │
                │ release non mergée  │
                └──────────┬──────────┘
                           │
                   ┌───────┴──────┐
                   │ Trouvée ?    │
                   └───┬─────┬───┘
                   Non │     │ Oui
                       ▼     ▼
                   (stop)   Merge dans
                            linux-flatpak
                            ┌────┴───────┐
                     Succès │            │ Conflit
                            ▼            ▼
                   ┌─────────────┐  ┌──────────┐
                   │ Push branch │  │ Issue ⚠️  │
                   │ (→ dev      │  │ conflit + │
                   │   build     │  │ fichiers  │
                   │   auto)     │  │ listés    │
                   │             │  └──────────┘
                   │ Stable ?    │
                   │  Oui → 1. Update appdata
                   │         2. Trigger build prod
                   │  Non → Dev build uniquement
                   │             │
                   │ Issue ✅    │
                   │ traçabilité │
                   └─────────────┘
```

#### Logique stable vs pre-release

| Type release | `isPrerelease` | Actions |
|-------------|----------------|---------|
| Stable (ex: `3.6.0`) | `false` | Merge + update appdata + push (→ dev build) + trigger prod build |
| Pre-release (ex: `3.6.0b1`) | `true` | Merge + push (→ dev build uniquement) |

#### Dispatch manuel

| Paramètre | Effet |
|-----------|-------|
| `upstream_tag` | Force le sync d'un tag spécifique (ex: `3.6.0`) |
| `skip_production` | Merge + dev build, mais pas de build production |

---

## Procédures

### Publier une nouvelle version stable

C'est **entièrement automatisé** via `sync-upstream.yml`. Le flux est :

1. L'upstream publie une release stable (ex: `3.6.0`)
2. Le cron détecte la nouvelle release (max 6h de délai)
3. Le workflow merge le tag, met à jour l'appdata, et déclenche le build production
4. Une Issue ✅ est créée pour traçabilité

**Si urgence** (ne pas attendre le cron) :

```
GitHub Actions → Sync Upstream Release → Run workflow
  upstream_tag: 3.6.0
```

### Rebuilder une version existante

Utile si un build a échoué ou si un secret a changé :

```
GitHub Actions → Publish Multi-Arch Flatpak Repo → Run workflow
  version_tag: 3.5.2
```

→ Reconstruit et publie dans `repo/` (production).

### Tester une pre-release

1. L'upstream publie une beta (ex: `3.6.0b1`)
2. Le sync automatique la merge et publie dans `repo-dev/`
3. Tester sur une machine Linux :
   ```bash
   flatpak update --user   # si canal dev installé
   ```

> **Note :** Les données ne risquent pas d'être corrompues : chaque version crée son propre dossier de données (ex: `sharly-chess-3.6.0b1/`).

### Modifier la configuration Flatpak

1. Modifier les fichiers dans `flatpak/configuration/` sur `linux-flatpak`
2. Pousser → le build dev se déclenche automatiquement
3. Vérifier dans GitHub Actions
4. Si OK et destiné à la production → lancer un rebuild manuel :
   ```
   GitHub Actions → Publish Multi-Arch Flatpak Repo → Run workflow
     version_tag: <version_actuelle>
   ```

### Résoudre un conflit de merge upstream

Si `sync-upstream.yml` crée une Issue ⚠️ :

```bash
git fetch upstream --tags
git checkout linux-flatpak
git merge <TAG>
# Résoudre les conflits...
git add .
git commit
git push
```

Le push déclenche automatiquement un build dev.

---

## Fichiers de configuration Flatpak

| Fichier | Rôle |
|---------|------|
| `flatpak/configuration/com.sharlychess.SharlyChess.json` | Manifest (app-id, runtime, modules, build-commands) |
| `flatpak/configuration/com.sharlychess.SharlyChess.desktop` | Entrée bureau (nom, icône, catégories) |
| `flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml` | Métadonnées AppStream (description, releases, screenshots) |
| `flatpak/scripts/launcher.py` | Lancement dans le sandbox Flatpak |
| `flatpak/scripts/flatpak_patches.py` | Correctifs runtime |
| `flatpak/scripts/generate_notice.py` | Génération NOTICE licences tiers |
| `scripts/sync_desktop_version.py` | Mise à jour version dans le .desktop |

### Quoi mettre à jour et quand

| Événement | Fichier(s) | Automatisé ? |
|-----------|------------|-------------|
| Nouvelle version upstream | `appdata.xml` (release notes) | ✅ Oui (`sync-upstream`) |
| Nouvelle version upstream | `.desktop` (version) | ✅ Oui (`sync_desktop_version.py` dans le build) |
| Changement de runtime GNOME | Manifest JSON (`runtime-version`) | ❌ Manuel |
| Nouvelle dépendance Python | `requirements-flatpak.txt` | ❌ Manuel |
| Changement de permissions | Manifest JSON (`finish-args`) | ❌ Manuel |
| Changement version Python | Manifest JSON + `PYTHONPATH` | ❌ Manuel |

---

## Permissions Flatpak

Configurées dans le manifest (`finish-args`) :

| Permission | Raison |
|-----------|--------|
| `--share=network` | Service web (Litestar/Uvicorn sur port 8080) + accès FFE, FIDE, Chess-Results |
| `--filesystem=home:rw` | Import/export de fichiers utilisateur (Documents, Téléchargements) |
| `--socket=wayland` | Affichage GUI (protocole moderne) |
| `--socket=x11` | Affichage GUI (compatibilité) |
| `--socket=pulseaudio` | Notifications sonores |
| `--device=dri` | Accélération GPU |
| `--env=PYTHONUNBUFFERED=1` | Logs Python en temps réel |
| `--env=PYTHONPATH=...` | Chemin modules Python |

---

## Stockage des données

Les données sont isolées par version dans le sandbox Flatpak :

```
~/.var/app/com.sharlychess.SharlyChess/data/
└── sharly-chess-X.Y.Z/
    ├── events/          # Tournois (.sce) et configuration (.scc)
    │   └── archives/    # Tournois archivés (.sca)
    ├── logs/            # Journal d'activité
    ├── tmp/             # Bases temporaires (FIDE, FFE, sessions)
    └── custom/          # Fichiers personnalisés
```

Le script `launcher.py` configure `XDG_DATA_HOME`, crée les sous-dossiers, et positionne le `CWD` dans le dossier de version. L'application utilise ensuite des chemins relatifs.

---

## Flathub (futur)

La publication sur Flathub nécessitera des adaptations :

1. **Pas d'accès réseau au build** : Utiliser `flatpak-pip-generator` pour pré-déclarer toutes les dépendances Python comme sources offline
2. **Soumission** : Fork de `flathub/flathub`, branche `new-pr`, soumettre le manifest adapté
3. **Mises à jour** : Via PR sur le dépôt Flathub

Pour l'instant, la distribution se fait exclusivement via le dépôt self-hosted sur GitHub Pages.
