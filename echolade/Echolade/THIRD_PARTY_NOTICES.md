# Third-party components

Echolade's own license is for you to choose; this repository does not ship one.
The components below are downloaded or installed by the setup scripts, not copied into this repository.
License names for Python packages were read from the installed package metadata; "not stated" means the
package metadata did not declare a license, so **check upstream before redistributing a bundle**.

| Component | Version tested | License | Notes |
|---|---|---|---|
| Kokoro-82M model + voices | v1.0 files | Apache-2.0 (per the model card) | https://huggingface.co/hexgrad/Kokoro-82M |
| kokoro-onnx | 0.6.1 | not stated in package metadata | ONNX runner for Kokoro |
| onnxruntime | 1.31.1 | MIT | |
| FastAPI / Starlette / Uvicorn | 0.162.0 / 1.10.0 / 0.54.0 | MIT / BSD-3-Clause / BSD-3-Clause | |
| Pydantic | 2.14.2 | MIT | |
| NumPy | 2.5.4 | BSD-3-Clause and others (see package) | |
| python-soundfile | 0.14.0 | BSD-3-Clause | uses libsndfile |
| psutil | 7.2.2 | BSD-3-Clause | |
| imageio-ffmpeg | 0.8.1 | BSD-2-Clause | downloads/bundles an FFmpeg binary whose own license depends on the build |
| espeakng-loader / phonemizer | 0.2.4 / 3.6.0 | not stated in package metadata | eSpeak NG, which they load, is understood to be GPL-3.0 upstream. Review before redistributing |

Running Echolade for yourself needs no further action. If you plan to **redistribute** a packaged build,
review the GPL-related items above (eSpeak NG, FFmpeg build) with the licenses of those projects.
