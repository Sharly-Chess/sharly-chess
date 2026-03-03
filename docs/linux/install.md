# Installing Sharly Chess on Linux

Installation guide for Linux users. All commands use `--user` mode (no system administrator rights required, except for the initial Flatpak installation).

---

## 1. Prerequisites: install Flatpak

### Fedora / Linux Mint / Pop!_OS

Flatpak is **already installed** by default. Skip to step 2.

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y flatpak
```

### Arch Linux / Manjaro

```bash
sudo pacman -S flatpak
```

### openSUSE

```bash
sudo zypper install flatpak
```

### Other distributions

See [flathub.org/setup](https://flathub.org/setup) for your distribution.

---

## 2. Graphical integration (optional)

To install applications from the software centre and open `.flatpakrepo` files by double-clicking:

### GNOME (Ubuntu, Fedora Workstation)

```bash
sudo apt install gnome-software-plugin-flatpak    # Ubuntu/Debian
sudo dnf install gnome-software                    # Fedora (already included)
```

> On Ubuntu, this adds "Software" (blue/white icon), distinct from "Ubuntu Software" (Snap Store).

### KDE Plasma (Kubuntu, KDE Neon)

```bash
sudo apt install plasma-discover-backend-flatpak   # Ubuntu/Debian
sudo dnf install discover                           # Fedora (already included)
```

---

## 3. Enable Flathub

Flathub is **not configured by default** on most distributions. It must be added manually. Sharly Chess needs it to download its dependencies (GNOME runtime).

```bash
# Add Flathub in user mode (no sudo required)
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

Verify that Flathub has been added:

```bash
flatpak remotes --user
# Should show "flathub" in the list
```

> **Note:** If Flathub is already configured at system level (`flatpak remotes` without `--user`), it will work too. But adding with `--user` is preferred as it requires no administrator rights.

---

## 4. Restart (required)

If you have just installed Flatpak for the **first time**, you **must restart** your computer. Without this:

- Icons will not appear in the menu
- Environment variables will not be correct
- The software centre will not see the Flatpak plugin

---

## 5. Install Sharly Chess

### CLI method (recommended)

```bash
flatpak remote-add --user --if-not-exists sharly-chess \
  https://flatpak.sharly-chess.com/sharly-chess.flatpakrepo

flatpak install --user sharly-chess com.sharlychess.SharlyChess
```

### Graphical method

1. Download [sharly-chess.flatpakrepo](https://flatpak.sharly-chess.com/sharly-chess.flatpakrepo)
2. Double-click the file → the software centre opens
3. Add the repository, then search for "Sharly Chess" and click **Install**

---

## Updates

Sharly Chess updates automatically alongside your other Flatpak applications. To force an update:

```bash
flatpak update --user
```

---

## Rolling back to a previous version

### 1. List available versions

```bash
flatpak remote-info --user --log sharly-chess com.sharlychess.SharlyChess
```

Find the commit hash corresponding to the desired version (e.g. "Version 3.5.1 (x86_64)").

### 2. Roll back to that version

```bash
flatpak update --user --commit=FULL_HASH com.sharlychess.SharlyChess
```

### 3. Pin to prevent automatic updates

```bash
flatpak pin --user com.sharlychess.SharlyChess
```

To remove the pin:

```bash
flatpak pin --user --remove com.sharlychess.SharlyChess
```

---


## Data storage

Application data is stored in an isolated directory, with a sub-folder per version:

```
~/.var/app/com.sharlychess.SharlyChess/data/
└── sharly-chess-X.Y.Z/
    ├── events/          # Tournaments (.sce) and configuration (.scc)
    │   └── archives/    # Archived tournaments (.sca)
    ├── logs/            # Activity log
    ├── tmp/             # Temporary databases (FIDE, FFE, sessions)
    └── custom/          # Custom files
```

### Backup

```bash
tar -czf sharly_chess_backup_$(date +%Y%m%d).tar.gz \
  ~/.var/app/com.sharlychess.SharlyChess/data/
```

### Restore

```bash
tar -xzf sharly_chess_backup_*.tar.gz -C ~/
```

---

## Complete uninstall

```bash
# Remove the application (keep data)
flatpak uninstall --user com.sharlychess.SharlyChess

# Remove the application AND all data
flatpak uninstall --user --delete-data com.sharlychess.SharlyChess

# Remove the repository
flatpak remote-delete --user sharly-chess

# (Optional) Also remove the dev repository
flatpak remote-delete --user sharly-chess-dev
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| App does not appear in menu | Did you restart after the first Flatpak installation? |
| GPG verification error | Add `--no-gpg-verify` to the `remote-add` command |
| Missing icon | `gtk-update-icon-cache ~/.local/share/icons/hicolor` |
| Missing runtime | `flatpak install --user flathub org.gnome.Platform//49` |
| "App not found" during install | Check that the remote is added: `flatpak remotes --user` |
