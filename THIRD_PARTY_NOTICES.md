# Third-party notices

Vslukh is distributed under GNU GPL-3.0-or-later. It depends on and, in its container
image, redistributes third-party software and model assets under their own terms. This
summary is informational; the upstream license text and package metadata are
authoritative.

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

## PyTorch and NumPy

- [PyTorch](https://pytorch.org/) provides the CPU inference runtime. Its installed
  package metadata records the expression `Apache-2.0 AND Apache-2.0 WITH LLVM-exception
  AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`.
- [NumPy](https://numpy.org/) converts the generated tensor to PCM samples. Its installed
  package metadata records the expression
  `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`.

Their exact versions and transitive dependency graph are recorded in `uv.lock`. The
installed wheels retain every file named by their `License-File` metadata.

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
