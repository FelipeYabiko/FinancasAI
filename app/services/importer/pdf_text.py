"""Step 1 — PDF to text lines, rebuilt from word positions to preserve table layout."""

import io
from dataclasses import dataclass

import pdfplumber

LINE_TOLERANCE = 3.0  # points: words whose `top` differ less than this share a line
CHAR_WIDTH = 4.5  # points per character cell when re-creating columns
LEFT_MARGIN = 30.0  # points ignored on the left of every page


class PdfTextError(ValueError):
    """User-facing extraction error (scanned PDF, encrypted, not a PDF...)."""


@dataclass
class PdfText:
    pages: list[list[str]]

    @property
    def lines(self) -> list[str]:
        return [line for page in self.pages for line in page]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _words_to_lines(words: list[dict]) -> list[str]:
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= LINE_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    lines = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        out = ""
        cursor = None
        for w in row:
            if cursor is not None:
                gap = w["x0"] - cursor
                if gap < CHAR_WIDTH * 1.5:
                    out += " "  # same phrase
                else:
                    # column gap: anchor the word to its absolute x position so columns
                    # (e.g. "Entradas" vs "Saídas") stay distinguishable in plain text
                    col = int(max(0.0, w["x0"] - LEFT_MARGIN) // CHAR_WIDTH)
                    out += " " * max(2, col - len(out))
            else:
                out = " " * int(max(0.0, w["x0"] - LEFT_MARGIN) // CHAR_WIDTH)
            out += w["text"]
            cursor = w["x1"]
        lines.append(out.rstrip())
    return [ln for ln in lines if ln.strip()]


def extract_pdf_text(data: bytes) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise PdfTextError("o arquivo enviado não é um PDF")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                words = page.extract_words(
                    keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5
                )
                pages.append(_words_to_lines(words))
    except PdfTextError:
        raise
    except Exception as exc:  # pdfminer raises a zoo of exceptions (encrypted, corrupted...)
        raise PdfTextError(f"não foi possível ler o PDF: {exc.__class__.__name__}") from exc
    if not any(pages):
        raise PdfTextError(
            "o PDF não contém texto selecionável (provavelmente é escaneado/imagem). "
            "OCR não é suportado: exporte o extrato em PDF original pelo app/site do banco."
        )
    return PdfText(pages=pages)
