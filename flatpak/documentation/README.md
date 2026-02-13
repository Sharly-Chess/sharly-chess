# Documentation Flatpak — Sharly Chess

Distribution Linux de Sharly Chess via Flatpak, avec builds automatisés multi-architecture (x86_64 + ARM64) et publication sur un dépôt OSTree auto-hébergé via GitHub Pages.

---

## Documents

| Document | Public cible | Contenu |
|----------|-------------|---------|
| [INSTALL.md](INSTALL.md) | **Utilisateurs** | Installation par distribution Linux, mises à jour, rollback, canal dev, dépannage |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | **Développeurs** | Architecture CI/CD, workflows, procédures, configuration Flatpak |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | **Mainteneur** | Clés GPG, GitHub Pages, secrets, configuration du déploiement |

---

## Liens rapides

- **Dépôt production** : https://gilleshorn.github.io/sharly-chess/repo/
- **Dépôt dev** : https://gilleshorn.github.io/sharly-chess/repo-dev/
- **Workflow build** : `.github/workflows/publish-multiarch.yml`
- **Workflow sync** : `.github/workflows/sync-upstream.yml`
- **Manifest Flatpak** : `flatpak/configuration/com.sharlychess.SharlyChess.json`
