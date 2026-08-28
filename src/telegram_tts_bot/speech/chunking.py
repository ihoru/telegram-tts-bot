"""Lossless text partitioning shared by local speech providers."""

MAX_CHUNK_LENGTH = 500
_CHUNK_BOUNDARIES = frozenset(".!?;:,…")


def chunk_text(text: str) -> list[str]:
    """Split text at natural boundaries without changing its content or order."""
    chunks: list[str] = []
    offset = 0
    while len(text) - offset > MAX_CHUNK_LENGTH:
        window = text[offset : offset + MAX_CHUNK_LENGTH]
        boundary = max(
            (
                index + 1
                for index, character in enumerate(window)
                if character.isspace() or character in _CHUNK_BOUNDARIES
            ),
            default=MAX_CHUNK_LENGTH,
        )
        chunks.append(text[offset : offset + boundary])
        offset += boundary
    if offset < len(text):
        chunks.append(text[offset:])
    return chunks
