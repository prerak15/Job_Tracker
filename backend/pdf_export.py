"""Compile a LaTeX resume to PDF locally.

Finds whichever TeX engine is installed and runs it in a throwaway directory.
Everything is deliberately conservative:

- shell-escape is disabled, so a document can't run arbitrary commands;
- the job runs in a temp dir with TEXMFOUTPUT pinned there, so nothing can be
  written back into the project;
- a wall-clock timeout kills a document that loops.

The LaTeX comes from the user or their own assistant, but a resume downloaded
from a job board and pasted in shouldn't be able to touch the machine.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# pdflatex first: the common resume templates use \pdfgentounicode, which is a
# pdfTeX primitive that the XeTeX-based engines don't provide.
ENGINES = ("pdflatex", "lualatex", "xelatex", "tectonic")

# MiKTeX and TeX Live don't always put themselves on PATH for the current
# process, so check the usual per-user install roots too.
EXTRA_DIRS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin",
    Path(os.environ.get("APPDATA", "")) / "MiKTeX" / "miktex" / "bin" / "x64",
    Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Roaming" / "TinyTeX" / "bin" / "windows",
    Path("C:/Program Files/MiKTeX/miktex/bin/x64"),
    Path("C:/texlive/2026/bin/windows"),
    Path("C:/texlive/2025/bin/windows"),
)

TIMEOUT_SECONDS = 120


class LatexNotInstalled(RuntimeError):
    pass


class LatexCompileError(RuntimeError):
    def __init__(self, message: str, log: str = "") -> None:
        super().__init__(message)
        self.log = log


def find_engine() -> tuple[str, str] | None:
    """Return (name, path) of the first available engine, or None."""
    for name in ENGINES:
        found = shutil.which(name)
        if found:
            return name, found
        for directory in EXTRA_DIRS:
            candidate = directory / f"{name}.exe"
            if candidate.exists():
                return name, str(candidate)
    return None


def available() -> dict[str, object]:
    engine = find_engine()
    if engine:
        return {"ok": True, "engine": engine[0], "path": engine[1]}
    return {
        "ok": False,
        "engine": None,
        "hint": (
            "No LaTeX engine found. Install MiKTeX (winget install MiKTeX.MiKTeX) "
            "or TinyTeX, then restart the backend."
        ),
    }


def _first_error(log: str) -> str:
    """Pull the first real TeX error out of a very long log."""
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!"):
            detail = line.lstrip("! ").strip()
            # The following l.<n> line says where it happened.
            for follow in lines[i + 1 : i + 6]:
                if follow.startswith("l."):
                    return f"{detail} (at {follow.strip()})"
            return detail
    missing = re.search(r"File `([^']+)' not found", log)
    if missing:
        return (
            f"Missing LaTeX package file {missing.group(1)}. "
            "Let MiKTeX install packages on the fly, or install it manually."
        )
    return "LaTeX failed to produce a PDF."


def compile_pdf(latex: str) -> bytes:
    """Compile LaTeX source and return the PDF bytes."""
    if not (latex or "").strip():
        raise LatexCompileError("There is no LaTeX source to compile.")

    engine = find_engine()
    if engine is None:
        raise LatexNotInstalled(str(available()["hint"]))
    name, executable = engine

    with tempfile.TemporaryDirectory(prefix="resume_tex_") as workdir:
        work = Path(workdir)
        source = work / "resume.tex"
        source.write_text(latex, encoding="utf-8")

        if name == "tectonic":
            command = [executable, "--outdir", str(work), "--keep-logs", str(source)]
        else:
            command = [
                executable,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                f"-output-directory={work}",
                str(source),
            ]
            # MiKTeX: fetch any missing package without prompting.
            if name != "lualatex":
                command.insert(1, "--enable-installer")

        env = {**os.environ, "TEXMFOUTPUT": str(work), "openout_any": "p", "openin_any": "p"}
        pdf = work / "resume.pdf"
        log_text = ""

        # Two passes so \titlerule, hyperref anchors and any refs settle.
        for _ in range(2):
            try:
                result = subprocess.run(
                    command,
                    cwd=work,
                    env=env,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise LatexCompileError(
                    f"LaTeX took longer than {TIMEOUT_SECONDS}s and was stopped."
                ) from exc

            log_file = work / "resume.log"
            log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
            log_text = log_text or (result.stdout or "") + (result.stderr or "")

            if not pdf.exists():
                raise LatexCompileError(_first_error(log_text), log_text[-4000:])

        return pdf.read_bytes()
