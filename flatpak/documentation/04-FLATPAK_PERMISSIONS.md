# 🔐 Permissions Flatpak pour Sharly Chess

Document expliquant les permissions requises pour que Sharly Chess fonctionne correctement en Flatpak.

## 📋 Vue d'ensemble

Sharly Chess est une application web avec les exigences suivantes :
- Service web (bind sur un port TCP)
- Accès au réseau (internet)
- Accès aux fichiers locaux (lecture/écriture)
- Interface graphique (GUI)

## 🔑 Permissions Configurées

### 1. Réseau TCP - Service Web
```json
"--share=network"
```

**Pourquoi** : Sharly Chess est une application web (Litestar + Uvicorn) qui :
- Écoute sur un port TCP (défaut : 8000)
- Communique avec les clients via HTTP/HTTPS
- Peut accéder aux services externes (FFE, Chess-Results)

**Implications** :
- L'application peut binder sur n'importe quel port
- Accès réseau illimité (interne et externe)
- Pas de sandboxing réseau

### 2. Système de Fichiers - Stockage Local
```json
"--filesystem=home:rw"
```

**Pourquoi** : L'application a besoin de :
- Créer des répertoires de travail (~/.local/share/sharly-chess/)
- Stocker les bases de données SQLite (persistance)
- Lire/écrire des fichiers de configuration
- Générer des rapports

**Implications** :
- Accès complet lecture/écriture au répertoire home
- Peut créer/modifier/supprimer des fichiers

### 3. Interface Graphique - Affichage
```json
"--socket=wayland",
"--socket=x11"
```

**Pourquoi** : Le launcher peut afficher une GUI :
- Wayland (nouveau protocole display)
- X11 (ancien protocole display, compatibilité)

**Implications** :
- L'application peut afficher des fenêtres
- Interactivité avec l'utilisateur

### 4. Audio (Optionnel)
```json
"--socket=pulseaudio"
```

**Pourquoi** : Support du son (chime de notification, etc.)

**Implications** :
- Accès aux périphériques audio

### 5. GPU (Pour performance)
```json
"--device=dri"
```

**Pourquoi** : Accès au GPU pour :
- Accélération vidéo (si GUI complexe)
- Meilleure performance de rendu

**Implications** :
- Utilisation des ressources GPU du système

### 6. Variables d'Environnement
```json
"--env=PYTHONUNBUFFERED=1",
"--env=PYTHONPATH=/app/lib/python3.13/site-packages"
```

**Pourquoi** :
- `PYTHONUNBUFFERED=1` : Output Python en temps réel (logs)
- `PYTHONPATH` : Chemin vers les modules Python installés

## 📦 Internet - Dépendances Python

**Spécification du manifest** :
```json
{
  "name": "python-dependencies",
  "build-commands": [
    "pip3 install --prefix=/app --find-links . -r requirements-flatpak.txt"
  ]
}
```

**Processus** :
1. À la **build** (création du package) : `--share=network` permet à `pip` de télécharger les packages
2. À l'**execution** (lancement) : `--share=network` permet l'accès aux services externes

**Important** : Les dépendances Python sont installées **une seule fois** au build, pas à chaque exécution.

## 🔍 Matrice des Permissions

| Permission | Type | Essentiellement | Raison |
|-----------|------|-----------------|--------|
| `--share=network` | Réseau | OUI | Service web + internet |
| `--filesystem=home:rw` | Fichiers | OUI | Stockage persistent (DB, config) |
| `--socket=wayland` | GUI | OUI | Affichage moderne |
| `--socket=x11` | GUI | OUI | Compatibilité anciens systèmes |
| `--socket=pulseaudio` | Audio | NON | Optionnel (notifications) |
| `--device=dri` | GPU | NON | Optionnel (performance) |

## 🚀 Configuration Finale

```json
"finish-args": [
  "--socket=wayland",
  "--socket=x11",
  "--socket=pulseaudio",
  "--share=network",
  "--filesystem=home:rw",
  "--device=dri",
  "--env=PYTHONUNBUFFERED=1",
  "--env=PYTHONPATH=/app/lib/python3.13/site-packages"
]
```

## ⚠️ Considérations de Sécurité

### Élevé
- `--share=network` : Accès réseau complet
- `--filesystem=home:rw` : Accès complet au home

### Modéré
- `--socket=wayland/x11` : Interaction utilisateur
- `--device=dri` : Accès GPU

### Faible
- `--socket=pulseaudio` : Audio
- Variables d'environnement : Configuration

## 📊 Comparaison avec AppImage

| Aspect | AppImage | Flatpak |
|--------|----------|---------|
| Isolation | Aucune | Sandbox |
| Réseau | Accès système | Contrôlé |
| Fichiers | Accès système | Contrôlé (homedir) |
| GUI | Accès système | Contrôlé |
| Dépendances | Bundlées | Partagées via runtime |

## 🔐 Profil de Sécurité

**Profil** : 🟡 PERMISSIF (nécessaire pour l'app)

**Justification** :
- Application web = nécessite `--share=network`
- Stockage persistent = nécessite `--filesystem=home:rw`
- Interface graphique = nécessite GUI sockets

**Alternative sécurisée** (si besoin) :
```json
"--filesystem=xdg-data/sharly-chess:rw",  // Limité à ~/.local/share/sharly-chess
"--network",                               // Réseau (mais pas socket wayland)
```

Mais cela **casserait l'application** car Sharly Chess a besoin de :
- Afficher une GUI complète
- Accéder à tous les fichiers de l'utilisateur

## 📝 Fichier de Configuration

Le manifest Flatpak final :
```
flatpak/configuration/com.sharlychess.SharlyChess.json
```

Voir la section `"finish-args"` pour les permissions exactes.

## 🧪 Test des Permissions

Après build, vérifier les permissions :
```bash
# Voir les permissions du manifest compilé
flatpak info com.sharlychess.SharlyChess

# Ou directement dans le manifest
cat /usr/share/app-info/xmls/org.gnome.Software.xml.d/com.sharlychess.SharlyChess.xml.in
```

## 📚 Documentation Officielle

- [Flatpak Portal Permissions](https://docs.flatpak.org/en/latest/portal-permissions.html)
- [Finish Args Reference](https://docs.flatpak.org/en/latest/manifest-format.html#finish-args)
- [Security Considerations](https://docs.flatpak.org/en/latest/security-considerations.html)
