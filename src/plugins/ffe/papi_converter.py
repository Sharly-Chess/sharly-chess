from pathlib import Path
import subprocess
import glob
import sqlite3

from common.exception import SharlyChessException
from common.tool_installer import PapiConverterInstaller


class PapiConverter:
    """Wrapper on the Papi converter
    (see https://github.com/Sharly-Chess/papi-converter)"""

    @property
    def executable_path(self) -> Path:
        return PapiConverterInstaller().executable_path

    def convert_player_database(self, source_file: Path, target_file: Path) -> bool:
        """Converts the .mdb player database to an SQLLite database."""
        # Clean up any existing temporary H2 database files to avoid conflicts
        # H2 creates files with patterns like: filename.mv.db, filename.trace.db

        # Clean up H2 files with various patterns
        cleanup_patterns = [
            str(target_file.parent / f"{target_file.stem}*.mv.db"),
            str(target_file.parent / f"{target_file.stem}*.trace.db"),
            str(target_file.parent / f"{target_file.name}*.mv.db"),
            str(target_file.parent / f"{target_file.name}*.trace.db"),
            str(target_file.with_suffix('.mv.db')),
            str(target_file.with_suffix('.trace.db')),
        ]

        for pattern in cleanup_patterns:
            for file_path in glob.glob(pattern):
                Path(file_path).unlink(missing_ok=True)

        # Also ensure the target file itself is clean
        target_file.unlink(missing_ok=True)

        # Create a temporary SQL dump file
        sql_dump_file = target_file.with_suffix('.sql')
        
        try:
            # First, create the SQL dump
            result = subprocess.run(
                [
                    self.executable_path,
                    '--playerdb',
                    str(source_file.resolve()),
                    str(sql_dump_file.resolve()),
                ],
                capture_output=True,
                encoding='utf-8',
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise SharlyChessException(
                f'PapiConverter execution failed with status {e.returncode}.\n'
                f'stdout: {e.stdout}\nstderr: {e.stderr}'
            )

        if not sql_dump_file.exists():
            raise SharlyChessException(
                'Player database conversion error: PapiConverter ran successfully but the SQL dump file was not created.'
            )

        try:
            # Create the SQLite database from the SQL dump using Python's sqlite3 module
            with open(sql_dump_file, 'r', encoding='utf-8') as dump_file:
                sql_content = dump_file.read()
                
            # Create the SQLite database and execute the SQL dump
            conn = sqlite3.connect(str(target_file))
            try:
                conn.executescript(sql_content)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            raise SharlyChessException(
                f'SQLite database creation failed: {e}'
            )
        finally:
            # Clean up the temporary SQL dump file
            sql_dump_file.unlink(missing_ok=True)

        if not target_file.exists():
            raise SharlyChessException(
                'Player database conversion error: SQLite database was not created.'
            )
        return True
