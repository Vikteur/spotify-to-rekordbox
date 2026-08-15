from pathlib import Path

from server.scanner.tags import AUDIO_EXTS, DRM_EXTS


def walk_library(root: Path) -> tuple[list[Path], int, list[str]]:
    """Recursively collect audio files under root.

    Returns (audio_files, drm_skipped_count, errors). Dot-directories are
    skipped; unreadable directories are reported, never fatal. `.m4p` files
    (DRM-locked iTunes/Apple Music) are counted so the user learns why those
    songs can't be used, but they are not scanned.
    """
    files: list[Path] = []
    drm_count = 0
    errors: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            errors.append(f"{directory}: {exc}")
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    stack.append(entry)
                    continue
                suffix = entry.suffix.lower()
                if suffix in AUDIO_EXTS:
                    files.append(entry)
                elif suffix in DRM_EXTS:
                    drm_count += 1
            except OSError as exc:
                errors.append(f"{entry}: {exc}")
    return files, drm_count, errors
