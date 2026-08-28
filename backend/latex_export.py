"""LaTeX resume support.

Resume versions can carry a `latex_content` alongside the plain-text `content`.
The plain text drives the dashboard preview and the .docx export; the LaTeX is
served as-is for download and compiled by the user (locally or on Overleaf).

This module also derives readable plain text back out of a LaTeX resume, so a
version that only has LaTeX still previews and still exports to Word. It
targets the widely used Jake Gutierrez / sb2nov template macros, and degrades
to generic stripping for anything else.
"""

from __future__ import annotations

import re
from typing import Any

# Characters LaTeX treats specially, when writing *into* a document.
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape(text: str) -> str:
    """Escape plain text for safe inclusion in a LaTeX document."""
    return "".join(_ESCAPES.get(ch, ch) for ch in text or "")


def _balanced_args(source: str, start: int, count: int) -> tuple[list[str], int]:
    """Read `count` brace-delimited arguments beginning at `start`."""
    args: list[str] = []
    i = start
    for _ in range(count):
        while i < len(source) and source[i] in " \t\r\n":
            i += 1
        if i >= len(source) or source[i] != "{":
            break
        depth, j = 0, i
        while j < len(source):
            if source[j] == "{":
                depth += 1
            elif source[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        args.append(source[i + 1 : j])
        i = j + 1
    return args, i


def _clean(fragment: str) -> str:
    """Reduce an inline LaTeX fragment to readable text."""
    text = fragment
    # \href{url}{label} -> label
    text = re.sub(r"\\href\s*\{[^}]*\}\s*\{([^}]*)\}", r"\1", text)
    # Formatting wrappers keep their contents.
    for macro in ("textbf", "textit", "underline", "emph", "small", "large", "Huge", "scshape"):
        text = re.sub(r"\\" + macro + r"\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(vspace|hspace)\s*\{[^}]*\}", "", text)
    # Purely decorative boxes go entirely, contents included — \raisebox holds a
    # glyph (a link arrow, say), not words, and its length argument is not text.
    text = re.sub(r"\\raisebox\s*\{[^}]*\}\s*\{[^{}]*\}", "", text)
    text = re.sub(r"\\[,;:!]", "", text)  # thin/medium/negative spaces
    text = re.sub(r"\\[a-zA-Z@]+\s*\*?", "", text)  # any remaining command
    text = text.replace("$|$", "|").replace("\\\\", " ")
    text = re.sub(r"\$\s*\$", "", text)  # math left empty by the strip above
    text = re.sub(r"[{}]", "", text)
    for escaped, plain in (
        (r"\&", "&"), (r"\%", "%"), (r"\$", "$"), (r"\#", "#"), (r"\_", "_"),
    ):
        text = text.replace(escaped, plain)
    # Longest first: "---" is an em dash, and "--" would otherwise eat its head.
    text = text.replace("---", "—").replace("--", "–")
    return re.sub(r"\s+", " ", text).strip(" |·-")


def _header_lines(header: str) -> list[str]:
    """Name and contact details from the block before the first \\section."""
    out: list[str] = []
    name = ""
    match = re.search(r"\\textbf\s*\{", header)
    if match:
        args, end = _balanced_args(header, match.end() - 1, 1)
        if args:
            name = _clean(args[0])
            # Drop the name group so it isn't repeated in the contact line.
            header = header[: match.start()] + header[end:]
    if name:
        out.append(name)

    # Whatever remains is the contact line, usually split across source lines.
    remainder = re.sub(r"\\(begin|end)\s*\{[^}]*\}", " ", header)
    # Collapse \href{url}{label} first: in real templates the two groups often
    # straddle a newline, and per-line cleaning would keep both url and label.
    remainder = re.sub(
        r"\\href\s*\{[^}]*\}\s*\{([^}]*)\}", r"\1", remainder, flags=re.S
    )
    # The template puts each contact item on its own source line ending in
    # "$|$", and _clean drops that trailing separator — so rejoin with it.
    pieces = [_clean(part) for part in remainder.split("\n")]
    joined = " | ".join(p for p in pieces if p)
    joined = re.sub(r"\s*\|\s*", " | ", joined).strip(" |")
    if joined:
        out.append(joined)
    return out


def to_plain_text(latex: str) -> str:
    """Best-effort plain-text rendering of a LaTeX resume."""
    if not latex:
        return ""

    body = latex
    start = body.find(r"\begin{document}")
    if start != -1:
        body = body[start + len(r"\begin{document}") :]
    end = body.find(r"\end{document}")
    if end != -1:
        body = body[:end]

    # Drop comment lines before anything else.
    body = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("%")
    )

    # The letterhead is loose text rather than macros, so handle it separately.
    first_section = body.find(r"\section")
    if first_section == -1:
        return "\n".join(_header_lines(body))
    out: list[str] = _header_lines(body[:first_section])
    body = body[first_section:]

    i = 0
    while i < len(body):
        if body[i] != "\\":
            i += 1
            continue

        match = re.match(r"\\([a-zA-Z@]+)", body[i:])
        if not match:
            i += 1
            continue
        command = match.group(1)
        after = i + match.end()

        if command == "section":
            args, i = _balanced_args(body, after, 1)
            if args:
                out.append("")
                out.append(_clean(args[0]).upper())
            continue

        if command == "resumeSubheading":
            args, i = _balanced_args(body, after, 4)
            parts = [_clean(a) for a in args]
            org, right, role, dates = (parts + ["", "", "", ""])[:4]
            head = org
            if role:
                head += f", {role}"
            trailing = " · ".join(p for p in (dates, right) if p)
            out.append("")
            out.append(f"{head} ({trailing})" if trailing else head)
            continue

        if command in ("resumeProjectHeading", "resumeSubSubheading"):
            args, i = _balanced_args(body, after, 2)
            parts = [_clean(a) for a in args if _clean(a)]
            if parts:
                out.append("")
                out.append(" — ".join(parts))
            continue

        if command in ("resumeItem", "resumeSubItem"):
            args, i = _balanced_args(body, after, 1)
            if args and _clean(args[0]):
                out.append(f"- {_clean(args[0])}")
            continue

        if command == "begin":
            args, i = _balanced_args(body, after, 1)
            continue

        if command == "end":
            args, i = _balanced_args(body, after, 1)
            continue

        if command == "item":
            # A bare \item, as used in the skills block: read to the end of the
            # surrounding group so \end{itemize} doesn't get treated as text.
            stop = min(
                (p for p in (body.find(r"\end", after), body.find("\n\n", after)) if p != -1),
                default=len(body),
            )
            for line in body[after:stop].split(r"\\"):
                cleaned = _clean(line)
                if cleaned:
                    out.append(cleaned)
            i = stop
            continue

        i = after

    # The contact line typically survives as loose text in the header block.
    lines = [ln.rstrip() for ln in out]
    collapsed: list[str] = []
    for line in lines:
        if not line and (not collapsed or not collapsed[-1]):
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def filename_for(resume: dict[str, Any], person: str = "") -> str:
    who = person or "Resume"
    label = resume.get("version_label") or resume.get("name") or ""
    stem = f"{who} {label}".strip() or "Resume"
    stem = re.sub(r"[^\w\s-]", "", stem).strip()
    stem = re.sub(r"[\s_-]+", "_", stem)
    return f"{stem[:80]}.tex"
