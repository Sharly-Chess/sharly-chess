**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Configuration et utilisation

Le logiciel Papi-web est utilisable immédiatement après installation..

## Gestion du serveur Papi-web (`server.bat`)

Le serveur Papi-web se lance en exécutant le script `server.bat`.

On arrête le serveur en tapant `Ctrl-C`.

## Interface avec le site fédéral (`ffe.bat`)

Les outils d'interface avec le site fédéral se lancent en exécutant le script `ffe.bat`.

> [!NOTE]
> Pour utiliser les outils d'interface avec le site fédéral sur les tournois de vos évènements, il est nécessaire de déclarer le numéro d'homologation et le code d'accès des tournois.

## Interface avec la plateforme ChessEvent (`chessevent.bat`)

Les outils d'interface avec la plateforme ChessEvent se lancent en exécutant le script `chessevent.bat`.

> [!NOTE]
> Pour utiliser les outils d'interface avec la plateforme ChessEvent sur les tournois de vos évènements, il est nécessaire de déclarer les identifiants d'accès à la plateforme ChessEvent.

## Configuration (optionnelle, `papi-web.ini`)

> [!NOTE]
> La configuration fournie par défaut dans le fichier `papi-web.ini` est suffisante pour la très grande majorité des cas, **vous n'avez normalement pas à modifier le fichier fourni par défaut**.

### Language (`[i18n]`)

#### locale

```
[i18n]
locale = en
```

Les languages implémentés sont visibles dans le répertoire [`/locale`](../locale).
Si cette option n'est pas trouvée dans le fichier de configuration, il est demandé à l'utilisateur·ice sa langue préférée, qui est inscrite dans le fichier de configuration.

#### experimental_locales

```
[i18n]
experimentale_locales = off
```

Par défaut les langues ayant un traducteur assigné sont présentés. En activant cette option, tous les langues du répertoire [`/locale`](../locale) peuvent être utilisés.

### Messages (`[logging]`)

#### level

```
[logging]
level = INFO
```

Pour obtenir plus de messages utiliser `level = DEBUG`.

### Réseau (`[web]`)

#### host

```
[web]
host = 0.0.0.0
```

La valeur `0.0.0.0` rend Papi-web accessible depuis tous les clients de votre réseau local (consulter votre administrateur·trice réseau pour restreindre les plages IP autorisées).

#### port

```
[web]
port = 80
```

La valeur par défaut `80` est celle classiquement utilisée par les serveurs web, qui rendra le serveur accessible depuis votre serveur à l'URL `http://127.0.0.1` ou bien `http://localhost`, et depuis un client du réseau local à l'URL `http://<ip_serveur>`. Si le port `80` est déjà utilisé sur votre serveur (cela est indiqué lorsqu'on lance `server.bat`), vous pouvez changer le port, par exemple pour `8080` (les URLs à utiliser seront alors `http://127.0.0.1::8080`, `http://localhost:8080` et `http://<ip_serveur>:8080`).

#### launch_browser

```
[web]
launch_browser = on
```

Par défaut, le navigateur web ouvre la page d'accueil au démarrage du serveur (pour ne pas ouvrir automatiquement la page d'accueil, utilisez `launch_browser = off`).

### Site fédéral (`[ffe]`)

#### upload_delay

```
[ffe]
upload_delay = 300
```
Le délai minimum entre deux téléchargements sur le site fédéral est par défaut fixé à `180` secondes (minimum `60` secondes).
