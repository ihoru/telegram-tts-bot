# Third-party notices

Vslukh is distributed under GNU GPL-3.0-or-later. It depends on and, in its container
image, redistributes third-party software and model assets under their own terms. This
summary is informational; the upstream license text and package metadata are
authoritative.

## Qwen3-TTS model and inference package

- Creator: Qwen Team, Alibaba Cloud
- Work: *Qwen3-TTS-12Hz-0.6B-CustomVoice*
- Model: [Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice)
- Immutable model revision: `85e237c12c027371202489a0ec509ded67b5e4b5`
- Inference package: `qwen-tts==0.1.1`
- Use: local mixed Russian-English synthesis with the `Aiden` or `Serena` speaker
- License: Apache License 2.0

The production image contains the inference package but not the model snapshot. The
explicit provisioner downloads and verifies the complete eleven-file snapshot before
runtime. The Apache 2.0 text distributed with `qwen-tts==0.1.1` is retained in
[`licenses/qwen3-tts-Apache-2.0.txt`](licenses/qwen3-tts-Apache-2.0.txt).

The two large model artifacts are integrity-pinned:

| File | SHA-256 |
| --- | --- |
| `model.safetensors` | `bc3c7e785eb961179c25450d1acff03f839e0002f2f3a5aeb67b5735c0fa2adb` |
| `speech_tokenizer/model.safetensors` | `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258` |

The full filename/checksum allowlist is maintained in
`src/telegram_tts_bot/speech/qwen_model.py`.

## Silero speech model

- Creator: Silero Team
- Work: *Silero Models: pre-trained text-to-speech models made embarrassingly simple*
- Project: [snakers4/silero-models](https://github.com/snakers4/silero-models)
- Attribution metadata revision:
  `d9355348e2781dc8fa25a135d1602c530afae24c`
- Artifact: [`v5_5_ru.pt`](https://models.silero.ai/models/tts/ru/v5_5_ru.pt)
- Use: local Russian speech synthesis with the `kseniya`, `xenia`, or `baya` speaker
- License: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
  (CC BY-NC-SA 4.0)
- Contact for separate terms: `hello@silero.ai`

The unmodified model weight is a separately licensed component. Its full terms are
retained in
[`licenses/silero-models-CC-BY-NC-SA-4.0.txt`](licenses/silero-models-CC-BY-NC-SA-4.0.txt).
The bundled weight may be used and redistributed only within the license's defined
NonCommercial restriction. Other use requires separate permission from Silero. Adapted
model material is subject to ShareAlike; Vslukh does not modify the distributed weight.
The application remains GPL-3.0-or-later, and no claim is made here about the license of
generated speech.

The artifact is integrity-pinned:

| File | SHA-256 |
| --- | --- |
| `v5_5_ru.pt` | `50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437` |

## PyTorch, TorchAudio, and NumPy

- [PyTorch](https://pytorch.org/) provides the CUDA Qwen and CPU Silero inference runtime.
  Its installed
  package metadata records the expression `Apache-2.0 AND Apache-2.0 WITH LLVM-exception
  AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`.
- [NumPy](https://numpy.org/) converts the generated tensor to PCM samples. Its installed
  package metadata records the expression
  `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`.

[TorchAudio](https://pytorch.org/audio/) supports the Qwen audio stack. Exact versions
and the complete transitive dependency graph are recorded in `uv.lock`. Installed
wheels retain the license files declared in their package metadata.

## Container runtime components

The production image is based on the official Python image and includes Debian's FFmpeg
and CA-certificate packages, plus SoX for the Qwen audio stack. Python is distributed
under the Python Software Foundation License. FFmpeg, SoX, and their linked libraries are
covered by the licenses reported by the specific Debian packages in the image.
Corresponding package copyright notices remain available under `/usr/share/doc` inside
the image.

## Other Python dependencies

The complete dependency graph and exact resolved versions are in `uv.lock`. Each package
retains its own copyright and license. Re-run the release SBOM generation after any lock
or base-image change; the tagged GitHub release contains an SPDX JSON inventory of the
actual published container.
