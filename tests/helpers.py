"""Programmatic audio fixtures — no ffmpeg, no checked-in binaries.

silent_mp3_bytes hand-assembles valid MPEG-1 Layer III frames (mutagen only
parses headers, so zeroed frame bodies are fine). write_wav uses the stdlib
`wave` module for files with exact durations.
"""

import struct
import wave
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TKEY, TXXX
from mutagen.mp3 import MP3

# MPEG-1 Layer III, 32 kbps (bitrate index 1), 44100 Hz (index 0), mono.
_FRAME_HEADER = bytes([0xFF, 0xFB, 0x10, 0xC0])
_FRAME_SIZE = 144 * 32000 // 44100  # 104 bytes, header included
_FRAMES_PER_SEC = 44100 / 1152


def silent_mp3_bytes(seconds: float = 1.0) -> bytes:
    frame = _FRAME_HEADER + b"\x00" * (_FRAME_SIZE - len(_FRAME_HEADER))
    return frame * max(1, round(seconds * _FRAMES_PER_SEC))


def write_mp3(path: Path, seconds: float = 1.0, *, artist: str | None = None,
              title: str | None = None, album: str | None = None,
              bpm: str | None = None, key: str | None = None,
              key_frame: str = "TKEY") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(silent_mp3_bytes(seconds))
    if artist or title or album or bpm:
        audio = MP3(path)
        audio.add_tags()
        audio.save()
        tags = EasyID3(path)
        if artist:
            tags["artist"] = artist
        if title:
            tags["title"] = title
        if album:
            tags["album"] = album
        if bpm:
            tags["bpm"] = bpm
        tags.save()
    if key:
        # rekordbox and Serato write TKEY; Mixed In Key writes TXXX:INITIALKEY.
        id3 = ID3(path)
        id3.add(
            TKEY(encoding=3, text=[key])
            if key_frame == "TKEY"
            else TXXX(encoding=3, desc="INITIALKEY", text=[key])
        )
        id3.save()
    return path


def write_wav(path: Path, seconds: float, framerate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        handle.writeframes(b"\x00\x00" * int(seconds * framerate))
    return path


def make_audio_tree(root: Path) -> dict[str, Path]:
    """A small realistic library tree covering the scanner's cases."""
    paths = {
        "tagged_accents": write_mp3(
            root / "House" / "am-i-wrong.mp3",
            artist="Étienne de Crécy", title="Am I Wrong", album="Super Discount",
        ),
        "tagged_extended": write_mp3(
            root / "House" / "substitution-ext.mp3",
            artist="Purple Disco Machine", title="Substitution (Extended Mix)",
        ),
        "untagged_numbered": write_mp3(root / "Untagged" / "01. Artist X - Some Song.mp3"),
        "untagged_plain": write_mp3(root / "Untagged" / "random_name.mp3"),
        "wav_exact": write_wav(root / "Wavs" / "Test Tone - Exact.wav", seconds=2.5),
        "hidden": write_mp3(root / ".hidden" / "skipme.mp3", title="Hidden"),
    }
    corrupt = root / "corrupt.mp3"
    corrupt.write_bytes(b"\x12\x34 this is definitely not audio \x56\x78" * 8)
    paths["corrupt"] = corrupt
    drm = root / "iTunes" / "old-purchase.m4p"
    drm.parent.mkdir(parents=True, exist_ok=True)
    drm.write_bytes(b"\x00\x00\x00\x20ftypM4P \x00" * 4)
    paths["drm"] = drm
    notes = root / "notes.txt"
    notes.write_text("not audio")
    paths["notes"] = notes
    return paths
