# _Sharly Chess_ - Files and folders

| Location                         | Type              | Format        | Usage                                                                                                         |
|----------------------------------|-------------------|---------------|---------------------------------------------------------------------------------------------------------------|
| **`sharly-chess-<version>.exe`** | **Program**       | Windows EXE   | The _Sharly Chess_ program itself                                                                             |
| **`events\.scc`**                | **Configuration** | SQLite        | The configuration of the _Sharly Chess_ application (`scc` stands for **S**harly **C**hess **C**onfiguration) |
| **`events\*.sce`**               | **Data**          | SQLite        | The event files (one file by event, `sce` stands for **S**harly **C**hess **E**vent)                          |
| **`papi\*.papi`**                | **Data**          | Access        | The Papi files (one by tournament, `papi` is the default folder for Papi files)                               |
| `custom\*.*`                     | Custom            | Any           | The customization files (background images)                                                                   |
| `tools\chessevent.bat`           | Script            | Windows batch | The script of the _ChessEvent_ plugin                                                                         |
| `tools\bbpPairings\*`            | Library           | Windows EXE   | The bbpPairings library used for Swiss pairing                                                                |
| `tmp\*.*`                        | Temporary         | Any           | The temporary files used by _Sharly Chess_                                                                    |
