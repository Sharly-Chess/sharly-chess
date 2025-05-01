**[Retour au sommaire de la documentation](../README.md)**

# Sharly Chess - Technical Appendix - Setting Up a Development Environment


You can use _PyCharm_ 2024.3.1.1 (_Community Edition_) on an up-to-date Windows 11 system.

Clone the _GitHub_ repository https://github.com/sharly-chess/sharly-chess and start playing ;-)

## Running Scripts from the Development Environment

### Starting the Web Server

```
python src/papi_web.py
```

Use the `--experimental` option to enable experimental features:

```
python src/papi_web.py --experimental
```

> :warning: USE EXPERIMENTAL FEATURES AT YOUR OWN RISK!

### Starting the Interface with the FFE Server

### Launching the interface with the FFE server

```
python src/papi_web.py --ffe
```

### Launching the interface with the ChessEvent platform

```
python src/papi_web.py --chessevent
```

## Configuring Authentication with the FFE Server

The `src/plugins/ffe/.credentials` file, used to connect to the federation's website, is not stored in the _GitHub_ repository.

It must be generated in each developer’s environment (ask other developers for the login credentials):

```
python scripts/ffe/generate_ffe_sql_server_credentials.py
```

## Creating the Windows Executable

The _Windows_ executable is automatically produced by a _GitHub_ action triggered by a new tag in the _GitHub_ repository.

- [View the _GitHub_ action](https://github.com/sharly-chess/sharly-chess/actions/workflows/export.yml)

An unpublished (draft) version is automatically created by the action with the release notes (https://github.com/Sharly-Chess/sharly-chess/blob/dev/RELEASE_NOTES.md) and must be approved before publication.

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
