**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Annexe technique : Configuration d'un environnement de développement

At this time, [pascalaubry](https://github.com/pascalaubry) uses PyCharm 2024.3.1.1 (Community Edition) on up-to-date Windows 11.

Simply checkout from https://github.com/papi-web-org/papi-web and play ;-)

## Lancement des scripts depuis l'environnement de développement

### Lancement du serveur web

```
python papi_web.py
```

Set environment variable ``PAPI_WEB_EXPERIMENTAL`` to ``1`` to enable expérimental features:

> [!WARNING]
> USE EXPERIMENTAL FEATURES AT YOUR OWN RISKS!

### Lancement de l'interface avec le serveur fédéral

```
python papi_web.py --server
```

### Lancement de l'interface avec la plateforme ChessEvent

```
python papi_web.py --chessevent
```

## Création d'un exécutable Windows pour diffusion

PyInstaller inclut dans l'exécutable Windows tous les paquets trouvés dans l'environnement virtuel, qu'ils soient utilisés ou non.

Un environnement virtuel dédié est donc utilisé ne comprenant que les paquets strictement nécessaires à l'exportation :

```
python -m venv .venv-export
.venv-export\Scripts\python.exe -m pip install --upgrade pip
.venv-export\Scripts\pip.exe install -e .[export]
```

L'archive ZIP est créée dans le répertoire `/export` et un environnement de test est créé dans `/export-test`.
