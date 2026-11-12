"""Real audio encoding and validation (spec 10). Uses FFmpeg for MP3 and resampling."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import soundfile as sf


class ExportError(Exception):
    """Message is safe to show to the user."""


def ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


def unique_path(directory: Path, base: str, ext: str) -> Path:
    """Never overwrite an existing file: append -2, -3 ... on collision."""
    candidate = directory / f"{base}.{ext}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{base}-{n}.{ext}"
        n += 1
    return candidate


def _run_ffmpeg(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    exe = ffmpeg_path()
    if not exe:
        raise ExportError("FFmpeg is needed for MP3, stereo and resampled exports but was not "
                          "found. Re-run the setup script, or export as WAV at 24 kHz mono.")
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ExportError("Audio encoding took too long and was stopped.") from exc
    except OSError as exc:
        raise ExportError("FFmpeg could not be started.") from exc


def export_audio(master_wav: Path, dest: Path, *, fmt: str, native_rate: int, sample_rate: int,
                 channels: int, mp3_bitrate: int, title: str) -> None:
    """Write ``dest`` atomically from the float master WAV. Raises ExportError."""
    part = dest.with_name(dest.name + ".part")
    try:
        plain_wav = fmt == "wav" and sample_rate == native_rate and channels == 1
        if plain_wav:
            # No FFmpeg needed: stream-copy the master as 16-bit PCM.
            with sf.SoundFile(str(master_wav)) as src, \
                    sf.SoundFile(str(part), "w", samplerate=src.samplerate, channels=1,
                                 subtype="PCM_16", format="WAV") as out:
                for block in src.blocks(blocksize=1 << 18, dtype="float32"):
                    out.write(block)
        else:
            args = ["-y", "-v", "error", "-i", str(master_wav), "-vn",
                    "-ac", str(channels), "-ar", str(sample_rate)]
            if fmt == "mp3":
                args += ["-c:a", "libmp3lame", "-b:a", f"{mp3_bitrate}k", "-f", "mp3"]
            else:
                args += ["-c:a", "pcm_s16le", "-f", "wav"]
            args += ["-metadata", f"title={title}", str(part)]
            result = _run_ffmpeg(args)
            if result.returncode != 0:
                raise ExportError("The audio file could not be encoded.")
        os.replace(part, dest)
    except ExportError:
        part.unlink(missing_ok=True)
        raise
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise ExportError("The audio file could not be saved. Check free disk space and "
                          "folder permissions.") from exc
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise ExportError("The audio file could not be created.") from exc


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(path: Path) -> float:
    """Decode the whole file with FFmpeg (proves it is valid) and return its duration."""
    result = _run_ffmpeg(["-hide_banner", "-v", "info", "-i", str(path), "-f", "null", "-"])
    if result.returncode != 0:
        raise ExportError("The exported file failed validation.")
    m = _DUR_RE.search(result.stderr)
    if not m:
        raise ExportError("The exported file's length could not be read.")
    h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mnt * 60 + s


def validate_output(path: Path, expected_seconds: float, fmt: str) -> float:
    """Confirm the file exists, is non-empty and decodes to roughly the expected length."""
    if not path.is_file() or path.stat().st_size < 64:
        raise ExportError("The exported file is empty or missing.")
    try:
        actual = sf.info(str(path)).duration if fmt == "wav" else probe_duration(path)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError("The exported file failed validation.") from exc
    if abs(actual - expected_seconds) > max(0.6, expected_seconds * 0.03):
        raise ExportError("The exported file's length does not match the generated audio.")
    return actual
