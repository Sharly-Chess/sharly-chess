# Sharly Chess Flatpak Installation Guide

This guide explains how to install and run the Sharly Chess Flatpak bundle on Linux distributions, specifically Fedora and Ubuntu.

## Prerequisites

### Fedora
Fedora usually comes with Flatpak installed by default. You just need to ensure the Flathub repository is enabled.

```bash
# Check if flatpak is installed
flatpak --version

# Add Flathub repository if missing
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

### Ubuntu
On Ubuntu, you need to install Flatpak and add the Flathub repository.

```bash
# Install Flatpak
sudo apt update
sudo apt install flatpak

# Install the GNOME Software Flatpak plugin (optional, for GUI management)
sudo apt install gnome-software-plugin-flatpak

# Add Flathub repository
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

> **Note**: On Ubuntu, you might need to restart your session (logout/login) after installing Flatpak for the paths to be updated correctly.

## Installation Steps

### 1. Download the Bundle
Download the `com.sharlychess.SharlyChess.flatpak` file from the GitHub Actions artifacts or your build output.

### 2. Install Dependencies (Runtimes)
Sharly Chess requires the GNOME Platform version 49. While Flatpak usually handles dependencies automatically, installing them explicitly can prevent issues.

```bash
flatpak install flathub org.gnome.Platform//49 org.gnome.Sdk//49
```

### 3. Install the Application

#### Method 1: Using the Official Repository (Recommended)
This method ensures you get automatic updates.

```bash
# Add the repository
flatpak remote-add --user --if-not-exists sharly-chess https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo

# Install Sharly Chess
flatpak install --user sharly-chess com.sharlychess.SharlyChess
```

#### Method 2: Using a Flatpak Bundle (Offline)
If you downloaded a `.flatpak` file manually:

Navigate to the directory where you downloaded the `.flatpak` file and install it. Using `--user` installs it for the current user only (no sudo required).

```bash
# Syntax: flatpak install --user <path-to-bundle>
flatpak install --user com.sharlychess.SharlyChess.flatpak
```

### 4. Run the Application
You can launch the application from your desktop environment's application menu, or via the command line:

```bash
flatpak run com.sharlychess.SharlyChess
```

## Troubleshooting

### "Runtime not found"
If you see an error indicating a missing runtime (e.g., `org.gnome.Platform/x86_64/49`), ensure you have added the Flathub remote and run the runtime installation step above.

### "No remote refs found for flathub"
This means the Flathub repository is not configured. Run the `remote-add` command listed in the Prerequisites section.

### Application crashes on startup
Check the logs by running from the terminal:
```bash
flatpak run com.sharlychess.SharlyChess
```
If you see Python dependency errors (e.g., `ModuleNotFoundError`), ensure the Flatpak was built with the correct `requirements-flatpak.txt`.

### Updating the Application
To update to a newer version of the `.flatpak` bundle:

```bash
# Uninstall the old version
flatpak uninstall com.sharlychess.SharlyChess

# Install the new bundle
flatpak install --user com.sharlychess.SharlyChess.flatpak
```
