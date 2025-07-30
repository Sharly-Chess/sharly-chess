# FreeTDS Export Integration

## Overview

Starting with version 2.8.3, Sharly Chess includes FreeTDS libraries in exported applications to provide SQL Server connectivity on macOS and Linux platforms.

## What's Included

### Libraries
- `libtdsodbc.so` / `libtdsodbc.0.so` - FreeTDS ODBC driver
- `libsybdb.5.dylib` - Core FreeTDS library  
- `libct.4.dylib` - Client library
- `libssl.3.dylib` - OpenSSL SSL library (dependency)
- `libcrypto.3.dylib` - OpenSSL crypto library (dependency)
- `libodbc.2.dylib` - UnixODBC library
- `libodbcinst.2.dylib` - UnixODBC installer library

### Configuration
- `setup_odbc.py` - Automatic ODBC environment setup script  
- ODBC configuration files for FreeTDS driver registration

## How It Works

1. **At Export Time**: The export script (`scripts/export/export.py`) automatically detects and includes FreeTDS libraries from the build machine.

2. **At Runtime**: The main application (`src/sharly_chess.py`) automatically calls `setup_odbc_environment()` when running as a PyInstaller bundle.

3. **ODBC Setup**: The setup script creates temporary ODBC configuration that points to the bundled FreeTDS libraries.

## Platform Support

- **Windows**: Uses built-in "SQL Server" driver (no FreeTDS needed)
- **macOS**: Uses bundled FreeTDS libraries  
- **Linux**: Uses bundled FreeTDS libraries

## Development vs Export

- **Development**: Requires `brew install freetds` (macOS) or equivalent package installation
- **Exported App**: All libraries bundled, no external dependencies required

## Connection Strategy

The application automatically tries drivers in this order:
1. **FreeTDS** - Primary choice for macOS/Linux
2. **SQL Server** - Fallback for Windows

FreeTDS uses TDS protocol versions in order of compatibility:
1. TDS 7.4 (SQL Server 2012+)
2. TDS 7.2 (Older SQL Server)  
3. TDS 7.0 (Very old SQL Server - most compatible)

## Troubleshooting

### Missing Libraries
If FreeTDS libraries are missing from the export:
- Ensure FreeTDS is installed on the build machine: `brew install freetds`
- Check that libraries exist in `/opt/homebrew/lib/` or `/usr/local/lib/`

### Connection Issues  
- The application will fallback through TDS versions automatically
- Check the application logs for "Successfully connected using strategy" messages
- Verify SQL Server is accessible from the target machine

## Technical Details

The export process:
1. Detects FreeTDS libraries on the build system
2. Includes them using PyInstaller's `--add-binary` option
3. Bundles the ODBC setup script
4. Creates runtime configuration that doesn't depend on system ODBC settings

This ensures exported applications work on machines without FreeTDS pre-installed.
