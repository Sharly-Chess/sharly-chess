# _Sharly Chess_ - Setting Up a Development Environment

You can use _PyCharm_ 2024.3.1.1 (_Community Edition_) on an up-to-date Windows 11 system.

Clone the _GitHub_ repository https://github.com/sharly-chess/sharly-chess and start playing ;-)

## Python version

Use Python 3.13 or newer (the project requires >=3.13). Verify your interpreter with:

```
python --version
```

## Running Scripts from the Development Environment

### Starting the Web Server

```
python src/sharly_chess.py
```

## Running with Docker

The server (headless console mode, no GUI) can also run in a container, for local development or for a self-hosted deployment. On Linux, the container detects a GTK-less environment and falls back to console mode automatically; the GUI code isn't used.

### Production

```
docker compose up -d --build
```

This builds the image, starts the server on port 8080, and persists its data in the named volume declared in [`docker-compose.yml`](../../docker-compose.yml).

### Development

[`docker-compose.dev.yml`](../../docker-compose.dev.yml) bind-mounts `src`, `default-files` and `locale` over the image's copies, so source changes are picked up on a container restart, without rebuilding the image:

```
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart
```

### Notes

- Federation-specific plugins (FFE, FIDE, Chess-Results) each need their own credentials file to work; without them they log a warning at startup instead of failing. The FFE, FIDE and FRA Schools local-database passwords can be set from the running app itself, in the "Data sources" modal of the settings page.
- The container is not meant to be exposed beyond the host it runs on: whichever client the host's Docker bridge network presents requests as (see `common.network.docker_gateway_ip`) is trusted as the local/administrator machine, the same way `127.0.0.1` is trusted outside of Docker.

## Configuring _FIDE_ local database decryption

The `src/.fide-database-enc-credentials` file, used to decrypt the _FIDE_ local database, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the credentials):

```
python scripts/fide/generate_fide_database_enc_credentials.py --password=xxx
```

## Configuring Authentication with the FFE Server

The `src/plugins/ffe/.sql-server-credentials` file, used to connect to the federation's website, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the login credentials):

```
python scripts/ffe/generate_ffe_sql_server_credentials.py --host=xxx --user=xxx --password=xxx --database=xxx
```

## Configuring _FFE_ local database decryption

The `src/plugins/ffe/.database-enc-credentials` file, used to decrypt the _FFE_ local database, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the credentials):

```
python scripts/ffe/generate_ffe_database_enc_credentials.py --password=xxx
```

## Configuring _FRA Schools_ local database decryption

The `src/plugins/fra_schools/.database-enc-credentials` file, used to decrypt the _FRA Schools_ local database, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the credentials):

```
python scripts/fra_schools/generate_fra_schooms_database_enc_credentials.py --password=xxx
```

## Creating the Windows Executable

The _Windows_ executable is automatically produced by a _GitHub_ action triggered by a new tag in the _GitHub_ repository.

- [View the _GitHub_ action](https://github.com/sharly-chess/sharly-chess/actions/workflows/export.yml)

An unpublished (draft) version is automatically created by the action with the release notes (https://github.com/Sharly-Chess/sharly-chess/blob/dev/RELEASE_NOTES.md) and must be approved before publication.

## Creating the Linux Flatpak

The Linux Flatpak is automatically built and published to a GitHub Pages repository by a GitHub action triggered by a new tag or manually.

- [View the GitHub action](https://github.com/Sharly-Chess/sharly-chess/actions/workflows/export.yml)

The Flatpak repository is hosted at `https://sharly-chess.github.io/sharly-chess/repo/`.

## Installing Tools and Libraries

As of version 2.6, libraries are no longer stored in the _GitHub_ repository and are installed:

- automatically in the developer's environment at the first server launch;
- manually by running the `install_libs.py` script.

```
python scripts/libs/install_libs.py
```

## Updating Federation Flags

Federation flags are stored in the _GitHub_ repository and can be updated using the `download_federation_flags.py` script:

```
python scripts/federation_flags/download_federation_flags.py
```
