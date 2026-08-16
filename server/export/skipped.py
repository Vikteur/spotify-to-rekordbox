"""A worklist of what the last scan could not use.

Two different jobs, so two labelled sections: DRM-locked files are ones to
buy, unreadable files are ones to repair or re-download. Paths are listed
plainly, one per line, so the file can be fed to a shell loop or opened in a
spreadsheet as easily as read.
"""

HEADER = "# Files skipped by the last scan"


def build_skipped_txt(
    folder: str,
    drm_files: list[str],
    drm_total: int,
    errors: list[dict],
) -> str:
    lines = [HEADER, f"# Folder: {folder}", ""]

    lines.append(f"# DRM-protected — rekordbox cannot play these ({drm_total})")
    if drm_files:
        lines.append(
            "# Apple Music subscription downloads and pre-2010 iTunes purchases."
        )
        lines.append("# They are locked to your Apple account; buy the track to use it.")
        lines.extend(drm_files)
        if drm_total > len(drm_files):
            lines.append(f"# ...and {drm_total - len(drm_files)} more, not listed.")
    else:
        lines.append("# (none)")
    lines.append("")

    lines.append(f"# Could not be read — corrupt, not audio, or unreadable ({len(errors)})")
    if errors:
        for error in errors:
            location = error.get("file") or "(folder)"
            message = (error.get("message") or "").strip()
            lines.append(f"{location}\t{message}" if message else location)
    else:
        lines.append("# (none)")
    lines.append("")
    return "\n".join(lines)
