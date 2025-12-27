# 🌐 Configuration Réseau Flatpak - Service Web Sharly Chess

Guide pour configurer et utiliser Sharly Chess en tant que service web dans Flatpak.

## 📌 Architecture Réseau

```
┌─────────────────────────────────────────────────┐
│ Utilisateur / Navigateur Web                     │
│ (http://localhost:8000)                          │
└────────────────────┬────────────────────────────┘
                     │ HTTP/TCP
                     ▼
┌─────────────────────────────────────────────────┐
│ Flatpak Sandbox                                  │
│  ├─ Sharly Chess (Litestar + Uvicorn)          │
│  │   ├─ Bind: 0.0.0.0:8000                      │
│  │   └─ Protocol: HTTP                           │
│  │                                               │
│  └─ Permission: --share=network ✅              │
│     (Permet d'écouter sur les ports TCP)        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ Système Hôte                                     │
│  ├─ Port 8000 (HTTP)                            │
│  └─ Port 8443 (HTTPS, si configuré)             │
└─────────────────────────────────────────────────┘
```

## 🔧 Configuration du Port

### Par Défaut
```python
# src/sharly_chess.py ou src/common/sharly_chess_config.py
PORT = 8000
HOST = "0.0.0.0"  # Écoute sur toutes les interfaces
```

### Modificable via Variable d'Environnement
```bash
# Dans le launcher Flatpak
SHARLY_CHESS_PORT=9000
SHARLY_CHESS_HOST=localhost
```

### Configuration dans le Manifest Flatpak
```json
{
  "command": "sharly-chess-launcher",
  "finish-args": [
    "--share=network"  // ✅ ESSENTIEL pour le bind TCP
  ]
}
```

## 🚀 Lancement

### Mode Normal (tous les interfaces)
```bash
flatpak run com.sharlychess.SharlyChess
```

Accès via : http://localhost:8000

### Mode Localhost Only (plus sécurisé)
```bash
flatpak run --env=SHARLY_CHESS_HOST=127.0.0.1 com.sharlychess.SharlyChess
```

Accès seulement depuis la machine locale.

### Port Personnalisé
```bash
flatpak run --env=SHARLY_CHESS_PORT=9000 com.sharlychess.SharlyChess
```

Accès via : http://localhost:9000

## 🔒 Considérations de Sécurité

### ✅ Sécurisé

```bash
# Localhost only (pas d'accès réseau externe)
flatpak run --env=SHARLY_CHESS_HOST=127.0.0.1 com.sharlychess.SharlyChess

# Avec firewall système
sudo ufw allow 8000/tcp from 192.168.1.0/24  # Limiter à un subnet
```

### ⚠️ À Surveiller

```bash
# ❌ JAMAIS en production sans HTTPS
# ❌ JAMAIS avec Host=0.0.0.0 sur internet public
# ❌ JAMAIS sans authentification
```

### 🛡️ Production

Pour une utilisation en production :

1. **HTTPS obligatoire**
   ```bash
   # Générer certificat auto-signé
   openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
   
   # Configurer dans Sharly Chess
   SHARLY_CHESS_SSL_CERT=/path/to/cert.pem
   SHARLY_CHESS_SSL_KEY=/path/to/key.pem
   ```

2. **Authentification**
   ```bash
   # Via Sharly Chess
   SHARLY_CHESS_AUTH_ENABLED=1
   ```

3. **Reverse Proxy**
   ```nginx
   # nginx
   server {
     listen 443 ssl;
     server_name sharlychess.example.com;
     
     ssl_certificate /etc/nginx/cert.pem;
     ssl_certificate_key /etc/nginx/key.pem;
     
     location / {
       proxy_pass http://localhost:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
     }
   }
   ```

## 🌍 Accès Réseau Externe

### Sharly Chess Server (local)
```
http://localhost:8000
https://192.168.1.100:8000  (sur le réseau local)
```

### Accès Internet Public (déconseillé sans proxy)
```
❌ http://mon-ip-publique:8000  (DANGER!)
✅ https://mon-domaine.com  (via nginx reverse proxy)
```

## 📡 Ports et Protocoles

| Port | Protocole | Service | Permission |
|------|-----------|---------|------------|
| 8000 | HTTP | Sharly Chess Web | `--share=network` |
| 8443 | HTTPS | Sharly Chess Secure | `--share=network` |
| 3306 | TCP | MySQL FFE | `--share=network` |
| 1433 | TCP | SQL Server FFE | `--share=network` |
| 443 | HTTPS | Internet (external APIs) | `--share=network` |

## 🔌 Debugging Réseau

### Vérifier le Bind
```bash
# Depuis le système hôte
netstat -tuln | grep 8000
lsof -i :8000

# Depuis Flatpak
flatpak run --command=netstat com.sharlychess.SharlyChess -tuln
```

### Tester la Connexion
```bash
# Depuis l'hôte
curl http://localhost:8000/api/health
curl http://192.168.1.100:8000/api/health

# Depuis Flatpak
flatpak run --command=curl com.sharlychess.SharlyChess http://localhost:8000
```

### Logs Réseau
```bash
# Logs de Sharly Chess
flatpak run com.sharlychess.SharlyChess 2>&1 | grep -i "listening\|port\|bind"

# Logs Flatpak
flatpak run --log-session com.sharlychess.SharlyChess
```

## 📊 Cas d'Usage

### Développement Local
```bash
# Port 8000, tout localhost
flatpak run com.sharlychess.SharlyChess
# → http://localhost:8000
```

### Test Réseau Local
```bash
# Port 8000, tous les interfaces
SHARLY_CHESS_HOST=0.0.0.0 flatpak run com.sharlychess.SharlyChess
# → http://192.168.1.100:8000 (depuis autres machines)
```

### Production (Kubernetes)
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sharly-chess
spec:
  containers:
  - name: sharly-chess
    image: ghcr.io/gilles
/chess2:latest
    ports:
    - containerPort: 8000
      protocol: TCP
    env:
    - name: SHARLY_CHESS_HOST
      value: "0.0.0.0"
    - name: SHARLY_CHESS_PORT
      value: "8000"
```

## 🔗 Intégration avec FFE

```
┌──────────────────────┐
│ Sharly Chess         │
│ (Flatpak sandbox)    │
└──────────┬───────────┘
           │ TCP:1433
           ▼
     ┌──────────────────┐
     │ SQL Server FFE   │
     │ (externe)        │
     └──────────────────┘
```

**Configuration** :
```bash
# Ces variables d'env sont lues par FFE plugin
FFE_SQL_SERVER_HOST=[REDACTED]
FFE_SQL_SERVER_PORT=1433
FFE_SQL_SERVER_USER=[REDACTED]
FFE_SQL_SERVER_PASSWORD=****
FFE_SQL_SERVER_DATABASE=[REDACTED]
```

Permission requise : `--share=network` ✅

## ✅ Checklist d'Installation

- [ ] `--share=network` configuré dans le manifest
- [ ] Port TCP 8000 accessible en local
- [ ] Pas de port en conflit
- [ ] HTTPS configuré (production)
- [ ] Authentification activée (production)
- [ ] Reverse proxy configuré (si exposé)
- [ ] Firewall allowlisting (si réseau local)
- [ ] Logs de démarrage consultés
- [ ] Test curl basique réussi
- [ ] Interface web accessible

## 🆘 Dépannage

### Port déjà utilisé
```bash
# Trouver le processus
lsof -i :8000

# Utiliser un autre port
flatpak run --env=SHARLY_CHESS_PORT=9000 com.sharlychess.SharlyChess
```

### Connection refused
```bash
# Vérifier le bind
netstat -tuln | grep 8000

# Vérifier les permissions Flatpak
flatpak info com.sharlychess.SharlyChess | grep network
```

### Timeout réseau
```bash
# Vérifier internet dans Flatpak
flatpak run --command=ping com.sharlychess.SharlyChess google.com
```

## 📚 Documentation Supplémentaire

- [Litestar Deployment](https://docs.litestar.dev/latest/topics/deployment.html)
- [Uvicorn Server](https://www.uvicorn.org/)
- [Flatpak Network Permissions](https://docs.flatpak.org/en/latest/portal-permissions.html#network)
