"""HTML job descriptions to plain text (card R55-B3).

Pure functions, no I/O. ATS payloads carry markup in three shapes: real HTML (Teamtailor,
JobPosting), entity-escaped HTML (Greenhouse `content`, which a board API returns as
`&lt;p&gt;...`), and plain text (Ashby/Lever `descriptionPlain`, manual input). All three
reach the same place, so one function reads all three; text without a tag comes back
unchanged, so it is safe to apply to every source.

Real tags are read by `html.parser`, which is linear in the input; the regular expressions
below are only linear scans for "is there a tag at all".
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

#: Longest input read, in characters. A job description is a few KB; anything past this is
#: cut rather than parsed, so a hostile or broken page cannot cost unbounded time.
MAX_INPUT_CHARS = 200_000

# A real tag opens with `<` and a letter or `!`; `a < b` and `x<5` are text.
_TAG_OPEN = re.compile(r"</?[a-z!]", re.IGNORECASE)
# Entity-escaped markup: `&lt;p`, or `&amp;lt;p` when escaped twice.
_ESCAPED_OPEN = re.compile(r"&(?:amp;)*lt;/?[a-z!]", re.IGNORECASE)
_ESCAPED_CLOSE = re.compile(r"&(?:amp;)*gt;", re.IGNORECASE)
_MAX_UNESCAPE_ROUNDS = 3

_SPACES = re.compile(r"[ \t ​]+")
_BLANK_LINES = re.compile(r"\n{3,}")

_DROPPED = frozenset({"script", "style", "noscript", "template"})
# Opening and closing tags of the dropped elements. `[^<>]{0,200}` keeps the scan linear.
_DROPPED_OPEN = {
    tag: re.compile(rf"<\s*{tag}(?![a-z0-9])[^<>]{{0,200}}>", re.IGNORECASE) for tag in _DROPPED
}
_DROPPED_CLOSE = {tag: re.compile(rf"<\s*/\s*{tag}\s*>", re.IGNORECASE) for tag in _DROPPED}
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCKS = frozenset(
    {"br", "p", "div", "ul", "ol", "dl", "dt", "dd", "tr", "table", "section", "article"}
    | {"header", "footer", "blockquote", "pre", "hr", "li"}
    | _HEADINGS
)
_CELLS = frozenset({"td", "th"})


def _has_real_tag(text: str) -> bool:
    opening = _TAG_OPEN.search(text)
    # HTMLParser can take a pathological amount of time buffering repeated
    # openers such as ``"<a" * 40_000``.  Without the tag terminator, this is
    # plain text rather than markup for our normalisation contract.
    return opening is not None and text.find(">", opening.end()) != -1


def _has_escaped_tag(text: str) -> bool:
    opening = _ESCAPED_OPEN.search(text)
    return opening is not None and _ESCAPED_CLOSE.search(text, opening.end()) is not None


def _without_unclosed_openers(text: str) -> str:
    """Remove the openers of `script`/`style`/`noscript`/`template` that never close.

    An element is dropped with its content only when its closing tag exists; an opener
    left without one is no element, and the text after it stays.
    """
    for tag in _DROPPED:
        openers = list(_DROPPED_OPEN[tag].finditer(text))
        excess = len(openers) - len(_DROPPED_CLOSE[tag].findall(text))
        for match in reversed(openers[len(openers) - excess :] if excess > 0 else []):
            text = text[: match.start()] + text[match.end() :]
    return text


class _TextExtractor(HTMLParser):
    def __init__(self, heading_marker: str, bullet: str) -> None:
        super().__init__(convert_charrefs=True)
        self._heading_marker = heading_marker
        self._bullet = bullet
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROPPED:
            self._skip += 1
        elif tag in _HEADINGS:
            self.parts.append(f"\n{self._heading_marker}")
        elif tag == "li":
            self.parts.append(f"\n{self._bullet}")
        elif tag in _BLOCKS:
            self.parts.append("\n")
        elif tag in _CELLS:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _DROPPED:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCKS:
            self.parts.append("\n")
        elif tag in _CELLS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None, *, heading_marker: str = "", bullet: str = "- ") -> str | None:
    """Plain text from an HTML, entity-escaped HTML or plain-text description.

    Entity-escaped HTML (no real tag, but `&lt;p&gt;`) is decoded, up to three times while
    it stays escaped, until real tags appear. Real HTML is never decoded before it is
    parsed, so `<p>R&amp;lt;D</p>` reads `R&lt;D`: entities are decoded exactly once, by
    the parser. `script`, `style` and comments go with their content; block tags (`p`,
    `div`, `br`, `li`, headings) become line breaks and `li` starts its line with `bullet`;
    inline tags vanish without splitting a word. `heading_marker` prefixes a heading line,
    for callers that tell headings apart. Whitespace is collapsed per line and blank lines
    to one.

    `None` stays `None`. Text with no tag, real or escaped, is plain text: its entities are
    decoded once and nothing else changes. `script`, `style`, `noscript` and `template` are
    dropped only when they close; an unclosed opener is removed and the text after it kept.
    Input past `MAX_INPUT_CHARS` is cut first. Applying the function again leaves clean text
    as it is, except text whose decoded form still reads as an entity (`R&lt;D`), which a
    second pass decodes once more.
    """
    if value is None:
        return None
    text = value[:MAX_INPUT_CHARS]
    if not _has_real_tag(text):
        for _ in range(_MAX_UNESCAPE_ROUNDS):
            if not _has_escaped_tag(text):
                break
            text = html.unescape(text)
            if _has_real_tag(text):
                break
        if not _has_real_tag(text):
            # No markup: plain text. Its entities are decoded once ("Tom &amp; Jerry").
            return html.unescape(text)
    extractor = _TextExtractor(heading_marker, bullet)
    extractor.feed(_without_unclosed_openers(text))
    extractor.close()
    lines = [
        _SPACES.sub(" ", line).strip()
        for line in "".join(extractor.parts).replace("\r", "").split("\n")
    ]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


__all__ = ("MAX_INPUT_CHARS", "html_to_text")
