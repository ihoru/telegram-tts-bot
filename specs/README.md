# Specifications

This directory is the source of truth for intentional changes to user-visible behavior,
public commands, providers and models, capacity, persistence, deployment, and BotFather
metadata.

## Workflow

1. Copy `TEMPLATE.md` to the next `NNNN-kebab-title.md` filename.
2. Keep the spec in `draft` while questions remain.
3. Change it to `accepted` only when every implementation decision and acceptance check
   is explicit and Open questions is empty.
4. Implement and verify the accepted contract.
5. Change it to `implemented` and record the implementing commit or release.

Retain rejected and superseded specs. An implemented spec is historical: make only
editorial corrections to it. Any behavioral change gets a new spec whose `supersedes`
field points at the old one, and the old one points back to its replacement.

Statuses are `draft`, `accepted`, `implemented`, `rejected`, and `superseded`.

## Index

| ID | Title | Status | Superseded by |
| --- | --- | --- | --- |
| 0001 | Initial Telegram TTS bot | superseded | 0002 |
| 0002 | Bilingual welcome and privacy policy | superseded | 0004 |
| 0003 | Record-voice chat action | implemented | - |
| 0004 | Configurable Silero voices | superseded | 0005 |
| 0005 | Local Qwen Aiden and Serena with Silero fallback voices | superseded | 0008 |
| 0006 | Chronological mixed-language audition archive | accepted | - |
| 0007 | Visible local Qwen provisioning and render progress | accepted | - |
| 0008 | Faster Qwen CUDA-graph runtime | accepted | - |
| 0009 | Qwen punctuation and CLI ergonomics | accepted | - |
| 0010 | Bounded fair rendering queue and aggregated progress | accepted | - |
| 0011 | Privacy-policy link in bot copy | accepted | - |
| 0019 | Read Aloud rebrand | accepted | - |

`BOTFATHER.md` contains the operational profile pack accepted by the current numbered
specification. Changes to that pack require a new numbered specification.
