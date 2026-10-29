"""Vault-directory file handling with reversible write, rename, and delete."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class TrackStorage:
    """Own the track directory: safe paths and file changes that can roll back.

    Each context manager applies a file change, yields so the caller can persist
    matching metadata, and restores the previous file state if that step fails.
    """

    def __init__(self, track_dir: Path, allowed_extensions: set[str]) -> None:
        self.track_dir = track_dir
        self.allowed_extensions = allowed_extensions
        self.track_dir.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        """Resolve a supported plain filename without allowing path escape."""
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Track name must be a plain filename without directories.")
        if Path(name).suffix.lower() not in self.allowed_extensions:
            raise ValueError("Unsupported track extension.")
        path = (self.track_dir / name).resolve()
        if path.parent != self.track_dir.resolve():
            raise ValueError("Track path must remain inside the vault directory.")
        return path

    def available_name(self, name: str) -> str:
        """Return ``name``, or ``stem_2.ext``, ``stem_3.ext``... if it is taken."""
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, counter = name, 2
        while self.path(candidate).exists():
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    def existing_path(self, name: str) -> Path:
        """Resolve ``name`` and require that the file exists."""
        path = self.path(name)
        if not path.is_file():
            raise FileNotFoundError(f"Track {name!r} was not found.")
        return path

    def track_files(self) -> list[Path]:
        """Return supported regular files in name order."""
        return [
            path
            for path in sorted(self.track_dir.iterdir())
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in self.allowed_extensions
        ]

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        """Replace a file atomically using a temporary sibling on one volume."""
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def writing(self, path: Path, data: bytes) -> Iterator[None]:
        """Write ``data``; restore the previous content (or absence) on failure."""
        previous = path.read_bytes() if path.is_file() else None
        self._atomic_write(path, data)
        try:
            yield
        except BaseException:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                self._atomic_write(path, previous)
            raise

    @contextmanager
    def renaming(self, source: Path, destination: Path) -> Iterator[None]:
        """Rename ``source``; move it back on failure."""
        source.rename(destination)
        try:
            yield
        except BaseException:
            destination.rename(source)
            raise

    @contextmanager
    def removing(self, path: Path) -> Iterator[None]:
        """Move ``path`` to a tombstone; delete it on success, restore on failure."""
        tombstone = path.with_name(f".{path.name}.{uuid4().hex}.deleting")
        path.replace(tombstone)
        try:
            yield
        except BaseException:
            tombstone.replace(path)
            raise
        tombstone.unlink(missing_ok=True)
