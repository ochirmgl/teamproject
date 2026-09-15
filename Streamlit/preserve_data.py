"""Verified portable SQLite/document snapshot; never replace a live database.

Run: python preserve_data.py --source DATA_DIRECTORY --output NEW_ARCHIVE.zip
The archive contains private application data. Keep it out of GitHub.
Stop writes while making a production migration snapshot.
"""
import argparse
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath


def snapshot(source, output):
    root, output = Path(source).resolve(), Path(output).resolve()
    database = root/'dms_system.db'
    if not database.is_file():
        raise ValueError('Source database does not exist.')
    if output.exists():
        raise ValueError('Choose a new archive filename; backups are never overwritten.')
    with tempfile.TemporaryDirectory() as temporary:
        copy = Path(temporary)/'dms_system.db'
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as live:
            with closing(sqlite3.connect(copy)) as saved:
                live.backup(saved)
        with closing(sqlite3.connect(copy)) as saved:
            if saved.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Database integrity check failed.')
            if saved.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Database contains broken relationships.')
            refs = set()
            for table in ('documents','document_versions'):
                if saved.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                    refs.update(r[0] for r in saved.execute(f'SELECT file_path FROM {table}') if r[0])
        files = {'dms_system.db':copy}
        for stored in refs:
            relative = Path(str(stored).replace('\\','/'))
            path = (root/relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Document reference is outside the data directory.')
            if not path.is_file():
                raise ValueError('A referenced document is missing; snapshot refused.')
            files[path.relative_to(root).as_posix()] = path
        manifest = {'format':1, 'files':{}}
        # Exclusive creation prevents replacing an existing backup on a race.
        with output.open('xb') as handle:
            with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
                for name, path in sorted(files.items()):
                    data = path.read_bytes()
                    archive.writestr(name,data)
                    manifest['files'][name] = hashlib.sha256(data).hexdigest()
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        verify(output)
        return len(files)


def verify(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate archive entries.')
        if set(archive.namelist()) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Archive manifest mismatch.')
        for name,digest in manifest['files'].items():
            if '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise ValueError('Unsafe archive entry.')
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Backup checksum mismatch.')
    return True


def restore_to_empty(archive_path, destination):
    """Restore only to a NEW directory, never over an existing live data folder."""
    verify(archive_path)
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        for name in manifest['files']:
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(archive.read(name))
    with closing(sqlite3.connect(root/'dms_system.db')) as saved:
        if saved.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('Restored database failed integrity check; do not use it.')
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    print(f'Verified snapshot: {snapshot(args.source,args.output)} files. Keep this archive private.')
