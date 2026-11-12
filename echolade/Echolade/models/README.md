# Models

Echolade needs two files here, downloaded by `setup.bat` / `setup.sh` (or `python scripts/download_models.py`):

| File | Size | Purpose |
|---|---|---|
| `kokoro-v1.0.onnx` | ~326 MB | Kokoro-82M speech model |
| `voices-v1.0.bin` | ~28 MB | 54 voice styles in 9 languages |

`model-manifest.json` pins the SHA-256 of each file. Downloads are refused if they do not match, and
Settings → Privacy → Verify re-checks them at any time.

The files are not included in the source zip because of their size. After downloading, Echolade works offline.
