# Third-party notices

Vslukh is distributed under GNU GPL-3.0-or-later. It depends on and, in its container
image, redistributes third-party software and model assets under their own terms. This
summary is informational; the upstream license text and package metadata are
authoritative.

## Piper

- Project: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)
- Use: local neural text-to-speech runtime, installed through `piper-tts`
- License: GNU GPL-3.0-or-later

Piper and its Python/transitive dependency versions are recorded exactly in `uv.lock`.

## `ru_RU-denis-medium` voice

- Source: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
- Immutable revision: `39ab474be869e9181350af6a65e4953eef67aaa0`
- Model card: [Denis medium](https://huggingface.co/rhasspy/piper-voices/blob/39ab474be869e9181350af6a65e4953eef67aaa0/ru/ru_RU/denis/medium/MODEL_CARD)
- Repository metadata license: MIT
- Training dataset license declared by the model card: CC0

The pinned upstream revision declares MIT in its repository metadata but does not contain
a standalone license file. The standard terms are retained in
[`licenses/piper-voices-MIT.txt`](licenses/piper-voices-MIT.txt), and the exact upstream
model card is copied into the runtime image beside these notices.

Bundled files are integrity-pinned:

| File | SHA-256 |
| --- | --- |
| `ru_RU-denis-medium.onnx` | `15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a` |
| `ru_RU-denis-medium.onnx.json` | `831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8` |

## Container runtime components

The production image is based on the official Python image and includes Debian's FFmpeg
and CA-certificate packages. Python is distributed under the Python Software Foundation
License. FFmpeg and its linked libraries are covered by the licenses reported by the
specific Debian packages in the image. Corresponding package copyright notices remain
available under `/usr/share/doc` inside the image.

## Other Python dependencies

The complete dependency graph and exact resolved versions are in `uv.lock`. Each package
retains its own copyright and license. Re-run the release SBOM generation after any lock
or base-image change; the tagged GitHub release contains an SPDX JSON inventory of the
actual published container.
