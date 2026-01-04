# ⚠️ RAPPEL CRITIQUE - 3 Exigences de Sharly Chess en Flatpak

Document de référence pour les 3 points critiques identifiés durant le développement.

---

## 1️⃣ Service Web avec Binding Réseau TCP

### Exigence
Sharly Chess est une **application web** (Litestar + Uvicorn) qui doit :
- **Écouter** sur un port TCP (défaut: 8000)
- **Binder** sur une interface réseau
- **Accepter** les connexions HTTP/HTTPS de clients

### Configuration Flatpak
```json
{
  "finish-args": [
    "--share=network"  // ✅ ESSENTIEL
  ]
}
```

### Ce que permet `--share=network`
✅ Binder sur port 8000 (TCP)
✅ Binder sur 127.0.0.1 ou 0.0.0.0
✅ Écouter les connexions entrantes
✅ Accéder aux services externes (FFE, Chess-Results)

### Sans cette permission
❌ Port binding échoue
❌ Service inaccessible
❌ Application non fonctionnelle

### Exemple d'Utilisation
```bash
# Lancer le service web
flatpak run com.sharlychess.SharlyChess

# Accéder depuis navigateur
curl http://localhost:8000
```

**Documentation** : Voir `05-NETWORK_CONFIGURATION.md`

---

## 2️⃣ Accès aux Fichiers Locaux - Read/Write

### Exigence
Sharly Chess doit :
- **Créer** des répertoires de travail
- **Lire et écrire** les bases de données SQLite
- **Stocker** les fichiers de configuration
- **Générer** les rapports et exports

### Configuration Flatpak
```json
{
  "finish-args": [
    "--filesystem=home:rw"  // ✅ ESSENTIEL (r/w explicite)
  ]
}
```

### Répertoires Accessibles
```
~/.var/app/com.sharlychess.SharlyChess/data/
└─ sharly-chess-X.Y.Z/
   ├─ events/
   │  ├─ .scc (Configuration)
   │  └─ *.sce (Tournois)
   ├─ logs/
   ├─ tmp/
   └─ custom/
```

### Sans cette permission
❌ Impossibilité d'importer/exporter des fichiers utilisateur
❌ Accès limité au sandbox

### Exemple de Fichiers Créés
```bash
# Après premier lancement (version 3.4.4)
~/.var/app/com.sharlychess.SharlyChess/data/sharly-chess-3.4.4/events/.scc
~/.var/app/com.sharlychess.SharlyChess/data/sharly-chess-3.4.4/logs/sharly-chess.log
```

### Vérification
```bash
# Vérifier l'accès en lecture/écriture
ls -la ~/.var/app/com.sharlychess.SharlyChess/data/sharly-chess-*/
cat ~/.var/app/com.sharlychess.SharlyChess/data/sharly-chess-*/logs/sharly-chess.log
```

**Documentation** : Voir `06-FILE_STORAGE.md`

---

## 3️⃣ Connexion Internet - Téléchargement Dépendances

### Exigence
À la **création du package Flatpak (build-time)** :
- Python pip doit télécharger les 37 packages Python
- Accès à PyPI (Python Package Index)
- Accès aux releases GitHub (libffi, OpenSSL)

### Configuration Flatpak
```json
{
  "finish-args": [
    "--share=network"  // ✅ MÊME PERMISSION
  ]
}
```

### Modules Affectés
```json
{
  "modules": [
    {
      "name": "libffi",
      "sources": [{
        "url": "https://github.com/libffi/libffi/releases/download/..."
        // ↑ Téléchargement réseau requis
      }]
    },
    {
      "name": "openssl",
      "sources": [{
        "url": "https://www.openssl.org/source/openssl-3.0.13.tar.gz"
        // ↑ Téléchargement réseau requis
      }]
    },
    {
      "name": "python-dependencies",
      "build-commands": [
        "pip3 install --prefix=/app -r requirements-flatpak.txt"
        // ↑ pip install depuis PyPI (réseau requis)
      ]
    }
  ]
}
```

### Processus
```
Build Phase (une seule fois lors de la création du package):
1. flatpak-builder démarre la sandbox
2. --share=network permet le téléchargement
3. pip télécharge de PyPI
4. libffi, OpenSSL téléchargés de GitHub
5. Tout compilé/installé dans le package

Runtime Phase (à chaque lancement):
- Les dépendances sont DÉJÀ dans le package
- Pas de téléchargement supplémentaire
- --share=network permet l'accès à FFE, Chess-Results APIs
```

### Sans cette permission
❌ Build échoue (pip ne peut pas télécharger)
❌ Manifest ne peut pas être résolu
❌ Aucun package ne peut être créé

### Vérification du Build
```bash
# Voir les téléchargements
flatpak-builder --verbose build-flatpak manifest.json 2>&1 | grep "http"

# Vérifier les packages installés
flatpak run --command=pip3 com.sharlychess.SharlyChess list
```

**Documentation** : Voir `04-FLATPAK_PERMISSIONS.md`

---

## 🔗 Relation Entre les 3 Points

```
Point 1: Réseau TCP     ↔ Point 2: Filesystem       ↔ Point 3: Internet
─────────────────────────────────────────────────────────────────────────
Application web         Données persistentes        Dépendances Python
écoute port 8000        stockées localement         téléchargées à la build

  ↓                            ↓                            ↓

Utilisateur se connecte   Les données survivent      Tout fonctionne
via navigateur            aux redémarrages           sans erreurs

  ↓                            ↓                            ↓

Sans cela:                Sans cela:                Sans cela:
❌ Service inaccessible   ❌ Pas de persistance      ❌ Build échoue
```

---

## ✅ Vérification Complète

### 1. Build avec Tous les Téléchargements
```bash
flatpak-builder --user --install build-flatpak \
  flatpak/configuration/com.sharlychess.SharlyChess.json
```

**Checks:**
- [x] Libffi téléchargé et compilé
- [x] OpenSSL téléchargé et compilé
- [x] 37 packages Python via pip
- [x] Sharly Chess installé

### 2. Service Web Accessible
```bash
# Lancer
flatpak run com.sharlychess.SharlyChess

# Tester (dans un autre terminal)
curl http://localhost:8000/api/health

# Résultat: {"status":"ok"} ou similaire
```

### 3. Données Persistantes
```bash
# Vérifier création de fichiers
ls ~/.var/app/com.sharlychess.SharlyChess/data/events/
ls ~/.var/app/com.sharlychess.SharlyChess/data/logs/

# Arrêter l'app (Ctrl+C)
# Relancer l'app
# Les données sont toujours là ✅
```

---

## 🚨 Erreurs Courantes

### Erreur 1: "Port already in use"
```
ERROR: Address already in use (0.0.0.0:8000)
```
**Cause** : Port 8000 déjà utilisé
**Solution** :
```bash
flatpak run --env=SHARLY_CHESS_PORT=9000 com.sharlychess.SharlyChess
```

### Erreur 2: "Connection refused"
```
curl: (7) Failed to connect to localhost port 8000
```
**Cause** : Service web ne s'est pas lancé correctement
**Vérification** :
```bash
# Voir les logs
flatpak run com.sharlychess.SharlyChess 2>&1 | grep -i "error\|listening"
```

### Erreur 3: "Permission denied" (filesystem)
```
ERROR: Cannot create events/
```
**Cause** : Problème de permissions dans `~/.var/app/...`
**Solution** : Vérifier les permissions du dossier data

### Erreur 4: "pip: command not found" (internet)
```
ERROR: pip: Failed to download requirements
```
**Cause** : `--share=network` manquant au build-time
**Solution** : Rebuild avec network permission

---

## 📖 Documentation de Référence

| Point | Documentation | Section |
|-------|---------------|---------|
| 1. TCP Binding | `05-NETWORK_CONFIGURATION.md` | Configuration du Port |
| 2. Filesystem | `06-FILE_STORAGE.md` | Répertoires Principaux |
| 3. Internet | `04-FLATPAK_PERMISSIONS.md` | Internet - Dépendances Python |

---

## 💾 Configuration Finale (Rappel)

```json
{
  "finish-args": [
    "--socket=wayland",
    "--socket=x11",
    "--socket=pulseaudio",
    "--share=network",              // ✅ Point 1 & 3
    "--filesystem=home:rw",         // ✅ Point 2
    "--device=dri",
    "--env=PYTHONUNBUFFERED=1",
    "--env=PYTHONPATH=/app/lib/python3.13/site-packages"
  ]
}
```

---

## 🎯 Résumé Ultra-Concis

| # | Exigence | Permission | Conséquence |
|---|----------|-----------|------------|
| 1 | Service Web TCP | `--share=network` | Port 8000 bindable ✅ |
| 2 | Fichiers Read/Write | `--filesystem=home:rw` | Données persistantes ✅ |
| 3 | Internet au Build | `--share=network` | Dépendances téléchargeables ✅ |

**Sans ces 3 points** → Application ne fonctionne pas.
**Avec ces 3 points** → Production-ready ! 🚀
