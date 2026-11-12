# Echolade

Fast, private, offline text-to-speech. Type or paste text, pick a voice, and get real MP3 or WAV audio
generated **on your own computer**. No account, no subscription, no cloud, no telemetry.

- **Engine:** Kokoro ONNX (82M-parameter neural model), CPU inference. 54 voices in 9 languages.
- **Stack:** Python + FastAPI backend, vanilla HTML/CSS/JS front end, FFmpeg for MP3 and conversion.
- **Privacy:** the server listens on `127.0.0.1` only; your text and audio are never sent anywhere.

## Install (one time)

Needs Python 3.11 or 3.12 (64-bit) and an internet connection for the first setup (about 360 MB).

| System | Run |
|---|---|
| Windows | double-click `setup.bat` |
| Linux / macOS | `./setup.sh` |

Setup creates a private virtual environment, installs pinned dependencies, then downloads the model and
**verifies it against a pinned SHA-256**. It can be re-run safely; interrupted downloads resume.

## Start

Windows: `start.bat` · Linux/macOS: `./start.sh`. Your browser opens at `http://127.0.0.1:8765`
(the next free port is used if 8765 is busy). Keep the window open while you use Echolade.
After setup, **no internet is needed**.

## Use

1. **Studio** – type, paste, or import a `.txt` / `.md` file. Drafts autosave in your browser.
2. **Voice** – click the voice card to browse, search, filter by language, preview (generated locally) and favourite.
3. **Delivery** – speed, paragraph pause, volume (loud settings are auto-limited so audio never clips).
4. **Export** – MP3 (96–256 kbps) or WAV; advanced: sample rate and mono/stereo.
5. **Generate** (`Ctrl+Enter`). Progress shows per segment. You can cancel at any time, listen to finished
   segments while the rest generate, retry failed segments, or export what finished.
6. **History** – replay, rename, download or delete past audio. Files live in `outputs/`.

### Performance profiles (Settings → Performance)
Automatic (default), Fastest, Balanced, High quality, Low memory, Custom. Profiles change **resource use**
(CPU threads, memory behaviour, segment length, idle unloading), not the model. *Run benchmark* times several
thread counts on your PC and Automatic uses the fastest. Settings → Diagnostics shows measured real-time
factor (generation time ÷ audio length; below 1.0 is faster than playback), first-audio latency, CPU and RAM.

### Honest limits
- Pitch, emphasis and emotion controls are **not shown** because Kokoro doesn't support them.
- Japanese, Mandarin and Hindi voices use a more limited phonemiser path and are marked "Limited".
- Cancelling takes effect after the segment currently being synthesised (usually a few seconds).
- Streaming is segment-by-segment (progressive playback), not sample-level streaming.

## Troubleshooting
| Problem | Fix |
|---|---|
| "Model isn't installed" banner | run the setup script, restart Echolade |
| "Can't reach Echolade" | the Echolade window was closed; start it again |
| MP3 export fails | FFmpeg missing: re-run setup, or export WAV 24 kHz mono |
| Slower than real time | normal on old CPUs: run the benchmark, try Fastest, close heavy apps |
| Model damaged | `python scripts/download_models.py` re-downloads anything that fails verification |
| Log files | `logs/echolade.log` (never contains your text) |

## Project layout
```
backend/   config, security, validation, hardware detection
  engines/   adapter interface + Kokoro engine + manager
  audio/     chunking, job runner, conversion/validation
  services/  settings, history, metrics, storage, voices, performance profiles
  api/       routers
frontend/  index.html, css/ (tokens, layout, components), js/ (modules)
scripts/   model downloader/verifier      tests/   pytest suite
```
New engines (e.g. Piper) implement `backend/engines/base.py:TTSEngine` and are registered in `EngineManager`.

## Security model
Host-header allow-list (DNS-rebinding), Origin check + per-launch session token on every write request (CSRF),
no CORS, strict CSP (no inline scripts/styles), 1 MB request cap, validated IDs/filenames/settings, outputs
confined to `outputs/`, no user text in logs or error messages. Azure/remote ONNX providers are blocked.

## Develop / test
```
pip install -r requirements-dev.txt
python -m pytest            # 60+ tests; model-based ones skip if the model isn't installed
```
Windows launch scripts and Windows/macOS hardware detection could not be run in the build environment (Linux);
see "Tested" in the hand-off notes.
