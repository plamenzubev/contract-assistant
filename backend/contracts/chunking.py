"""
Recursive character splitter for breaking text into chunks.

The idea: we split along natural boundaries in a hierarchy — first on blank
lines (paragraphs), then on lines, then on sentences, and finally on words.
Every atomic piece is guaranteed to be <= chunk_size. We then reassemble
adjacent pieces into chunks of ~chunk_size, carrying a little overlap between
them so context isn't cut at the seam.

Note: whitespace is normalized (consecutive spaces/newlines collapse to a
single one) — the content is faithful, only the formatting is smoothed out.
"""

# Separator hierarchy: from the coarsest boundary to the finest.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_recursive(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Splits the text into atomic pieces, each <= chunk_size (best effort)."""
    sep = separators[0]
    rest = separators[1:]

    if sep == "":
        # No more separators — hard-split by chunk_size.
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    pieces: list[str] = []
    for part in text.split(sep):
        part = part.strip()
        if not part:
            continue
        if len(part) <= chunk_size:
            pieces.append(part)
        else:
            # Still too large → drop down to a finer separator.
            pieces.extend(_split_recursive(part, rest, chunk_size))
    return pieces


def split_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Returns a list of chunks (strings) of approximate size, with overlap."""
    text = text.strip()
    if not text:
        return []

    pieces = _split_recursive(text, _SEPARATORS, chunk_size)

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for piece in pieces:
        # If adding this would overflow the current chunk — close it...
        if buf and buf_len + len(piece) + 1 > chunk_size:
            chunks.append(" ".join(buf))
            # ...and start a new chunk with overlap from the end of the previous one.
            tail: list[str] = []
            tail_len = 0
            for prev in reversed(buf):
                if tail_len + len(prev) + 1 > overlap:
                    break
                tail.insert(0, prev)
                tail_len += len(prev) + 1
            buf = tail
            buf_len = tail_len

        buf.append(piece)
        buf_len += len(piece) + 1

    if buf:
        chunks.append(" ".join(buf))

    return chunks
