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

## Configuring _FFE_ local database unzipping

The `src/plugins/ffe/.database-enc-credentials` file, used to decrypt the _FFE_ local database, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the credentials):

```
python scripts/ffe/generate_ffe_database_enc_credentials.py --password=xxx
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
