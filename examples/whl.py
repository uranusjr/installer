"""Install from a .whl file.
"""

import argparse
import codecs
import contextlib
import errno
import os
import sys
import zipfile

import six

from installer._compat import pathlib
from installer._compat.typing import TYPE_CHECKING
from installer.layouts import DistInfo
from installer.records import RecordItem, parse_record_file, write_record_file

if TYPE_CHECKING:
    from typing import Any, ContextManager, Dict, IO, Iterator


def _wrap_as_io_str(f):
    # type: (IO[six.binary_type]) -> Iterator[str]
    if not six.PY3:
        return f
    return codecs.getreader("utf-8")(f)


def _makedirs_exist_ok(path):
    # type: (pathlib.Path) -> None
    """Implement ``Path.mkdir(parents=True, exist_ok=True)`` Python 2.
    """
    try:
        os.makedirs(str(path))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class ZipFileInstaller(object):
    """Install a local wheel.
    """

    def __init__(self, name, dist_info, zip_file_handle):
        # type: (str, DistInfo, zipfile.ZipFile) -> None
        self._name = name
        self._dist_info = dist_info
        self._zip_file_handle = zip_file_handle

    @classmethod
    @contextlib.contextmanager
    def from_wheel_path(cls, name, wheel_path):
        # type: (str, pathlib.Path) -> Iterator[ZipFileInstaller]
        project_name, project_version, _ = wheel_path.stem.split("-", 2)
        with zipfile.ZipFile(str(wheel_path)) as zf:
            entry_names = (name.lstrip("/").split("/", 1)[0] for name in zf.namelist())
            dist_info = DistInfo.find(project_name, project_version, entry_names)
            yield cls(name, dist_info, zf)

    @contextlib.contextmanager
    def _open_adjacent_tmp_for_write(self, path, **kwargs):
        # type: (pathlib.Path, Any) -> Iterator[IO[Any]]
        _makedirs_exist_ok(path.parent)
        temp = path.with_name("{}.tmp.{}".format(path.name, self._name))
        with temp.open(**kwargs) as f:
            yield f
        temp.replace(path)

    def _open_target_for_write(self, path, binary=False):
        # type: (pathlib.Path, bool) -> ContextManager[IO[Any]]
        if binary:
            kwargs = {"mode": "wb"}
        else:
            kwargs = {"mode": "w", "encoding": "utf-8"}
        return self._open_adjacent_tmp_for_write(path, **kwargs)

    def _open_csv_for_write(self, path):
        # type: (pathlib.Path) -> ContextManager[IO[Any]]
        if sys.version_info < (3,):
            kwargs = {"mode": "wb"}
        else:
            kwargs = {"mode": "w", "newline": "", "encoding": "utf-8"}
        return self._open_adjacent_tmp_for_write(path, **kwargs)

    def _install_record_item(self, item, directory):
        # type: (RecordItem, pathlib.Path) -> None
        with self._zip_file_handle.open(str(item.path)) as f:
            data = f.read()
        item.raise_for_validation(data)
        target = directory.joinpath(item.path)
        with self._open_target_for_write(target, binary=True) as f:
            f.write(data)
        # TODO: Handle file permission and other metadata.

    def _iter_installed_record_items(self, directory):
        # type: (pathlib.Path) -> Iterator[RecordItem]
        with self._zip_file_handle.open(str(self._dist_info.record)) as f:
            for item in parse_record_file(_wrap_as_io_str(f)):
                self._install_record_item(item, directory)
                yield item

    def _iter_installed_scripts(self, directory):
        # type: (pathlib.Path) -> Iterator[RecordItem]
        return iter(())  # TODO: Implement me.

    def _write_additional_metadata(self, directory):
        # type: (pathlib.Path) -> Iterator[RecordItem]
        installer = directory.joinpath(self._dist_info.installer)
        with self._open_target_for_write(installer) as f:
            f.write(self._name)
        yield RecordItem(self._dist_info.installer, None, None)
        # TODO: Write direct_url.json.

    def _write_record(self, directory, installed_items):
        # type: (pathlib.Path, Dict[pathlib.PurePosixPath, RecordItem]) -> None
        record = self._dist_info.record
        installed_items[record] = RecordItem(record, None, None)
        with self._open_csv_for_write(directory.joinpath(record)) as f:
            write_record_file(f, installed_items.values())

    def install(self, directory):
        # type: (pathlib.Path) -> None
        items = {r.path: r for r in self._iter_installed_record_items(directory)}
        # TODO: Install .data directory.
        items.update((r.path, r) for r in self._iter_installed_scripts(directory))
        items.update((r.path, r) for r in self._write_additional_metadata(directory))
        self._write_record(directory, items)
        # TODO: Compile .pyc files.


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=pathlib.Path)
    parser.add_argument("dest", type=pathlib.Path)
    parser.add_argument("--installer", default="pypa-installer")

    options = parser.parse_args(args)
    with ZipFileInstaller.create(options.installer, options.wheel) as installer:
        installer.install(options.dest)


if __name__ == "__main__":
    main()
