#!/usr/bin/env python3
"""
rename_pdfs_by_title.py

Rename PDF papers in a directory using the title found inside each PDF.

Strategy:
1. Try embedded PDF metadata.
2. If metadata is missing/bad, inspect the first page and infer the title
   from large-font text near the top.
3. Sanitize the title into a safe filename.
4. Rename while avoiding collisions.

Examples:
    python rename_pdfs_by_title.py ~/Downloads/papers
    python rename_pdfs_by_title.py ~/Downloads/papers --dry-run
    python rename_pdfs_by_title.py ~/Downloads/papers --recursive
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF is not installed.")
    print("Install it with:")
    print("    pip install pymupdf")
    sys.exit(1)


BAD_METADATA_TITLES = {
    "",
    "untitled",
    "document",
    "microsoft word",
    "microsoft word - document1",
    "latex",
    "paper",
    "article",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def looks_like_bad_title(title: str, original_stem: str) -> bool:
    """Reject obviously useless metadata titles."""
    t = normalize_space(title)
    if not t:
        return True

    low = t.lower().strip()

    if low in BAD_METADATA_TITLES:
        return True

    if low == original_stem.lower():
        return True

    if low.endswith(".pdf"):
        return True

    # URLs / file paths are not useful titles.
    if "http://" in low or "https://" in low:
        return True

    if "/" in t or "\\" in t:
        return True

    # Very short metadata is usually not a paper title.
    if len(t) < 8:
        return True

    # Common garbage metadata produced by applications.
    garbage_terms = [
        "acrobat distiller",
        "pdfcreator",
        "pdf-xchange",
        "adobe indesign",
        "microsoft powerpoint",
    ]
    if any(g in low for g in garbage_terms):
        return True

    return False


def title_from_metadata(doc, original_stem: str):
    metadata = doc.metadata or {}
    title = normalize_space(metadata.get("title", ""))

    if not looks_like_bad_title(title, original_stem):
        return title

    return None


def get_lines_with_font_info(page):
    """
    Return text lines with approximate font size and bounding box.
    Each item:
        {
          "text": ...,
          "size": max font size in line,
          "y0": ...,
          "y1": ...,
          "x0": ...,
          "x1": ...
        }
    """
    data = page.get_text("dict")
    lines = []

    for block in data.get("blocks", []):
        if "lines" not in block:
            continue

        for line in block["lines"]:
            spans = line.get("spans", [])
            if not spans:
                continue

            text = normalize_space(" ".join(span.get("text", "") for span in spans))
            if not text:
                continue

            sizes = [float(span.get("size", 0)) for span in spans if span.get("text", "").strip()]
            if not sizes:
                continue

            bbox = line.get("bbox", (0, 0, 0, 0))

            lines.append(
                {
                    "text": text,
                    "size": max(sizes),
                    "avg_size": sum(sizes) / len(sizes),
                    "x0": float(bbox[0]),
                    "y0": float(bbox[1]),
                    "x1": float(bbox[2]),
                    "y1": float(bbox[3]),
                }
            )

    return lines


def is_probable_non_title_line(text: str) -> bool:
    low = text.lower().strip()

    if not low:
        return True

    # Typical journal / conference / header material.
    patterns = [
        r"^arxiv:",
        r"^doi\b",
        r"^https?://",
        r"^www\.",
        r"^proceedings of\b",
        r"^ieee\b",
        r"^acm\b",
        r"^springer\b",
        r"^elsevier\b",
        r"^journal of\b",
        r"^vol\.?\s*\d+",
        r"^volume\s+\d+",
        r"^copyright\b",
        r"^©",
        r"^\d{4}\b",
    ]

    if any(re.search(p, low) for p in patterns):
        return True

    # Author/email-like lines.
    if "@" in text:
        return True

    # Bare numbering or page identifiers.
    if re.fullmatch(r"[\d\s\-–—().]+", text):
        return True

    return False


def title_from_first_page(doc):
    """
    Infer the title from large-font lines near the top of page 1.

    This is tuned for academic PDFs where the title is usually:
    - near the top of page 1
    - among the largest text on the page
    - one to several adjacent lines
    """
    if len(doc) == 0:
        return None

    page = doc[0]
    page_height = page.rect.height
    lines = get_lines_with_font_info(page)

    if not lines:
        return None

    # Restrict mostly to the upper part of the page.
    top_lines = [
        ln for ln in lines
        if ln["y0"] <= page_height * 0.42
        and not is_probable_non_title_line(ln["text"])
    ]

    if not top_lines:
        return None

    # Prefer larger font sizes.
    max_size = max(ln["size"] for ln in top_lines)

    # Title lines can have tiny font-size inconsistencies.
    size_threshold = max_size - max(1.0, max_size * 0.10)

    candidates = [
        ln for ln in top_lines
        if ln["size"] >= size_threshold
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x["y0"], x["x0"]))

    # Build groups of nearby large-font lines. Multi-line titles usually
    # have modest vertical spacing between title rows.
    groups = []
    current = []

    for ln in candidates:
        if not current:
            current = [ln]
            continue

        prev = current[-1]
        gap = ln["y0"] - prev["y1"]

        # Allow normal title wrapping, but stop before author section.
        if gap <= max(18, max_size * 1.5):
            current.append(ln)
        else:
            groups.append(current)
            current = [ln]

    if current:
        groups.append(current)

    def group_score(group):
        text = normalize_space(" ".join(x["text"] for x in group))

        # Penalize author-like groups or very long blocks.
        score = sum(x["size"] for x in group)

        if len(text) < 10:
            score -= 30

        if len(text) > 300:
            score -= 50

        comma_count = text.count(",")
        if comma_count >= 4:
            score -= 20

        # Prefer groups appearing near the top.
        score -= group[0]["y0"] * 0.02

        return score

    groups.sort(key=group_score, reverse=True)

    for group in groups:
        title = normalize_space(" ".join(x["text"] for x in group))

        if 10 <= len(title) <= 300 and not is_probable_non_title_line(title):
            return title

    return None


def clean_title(title: str, max_length: int = 180) -> str:
    """
    Convert title to a filesystem-safe filename stem.
    """
    title = normalize_space(title)

    # Replace forbidden filename characters.
    title = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", title)

    # Normalize common Unicode punctuation a little.
    title = title.replace("–", "-").replace("—", "-")
    title = title.replace("“", '"').replace("”", '"')
    title = title.replace("’", "'")

    # Remove characters Windows dislikes at filename end.
    title = title.strip(" .")

    # Avoid excessive repeated punctuation/spaces.
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"\.{3,}", "...", title)

    # Limit filename length.
    if len(title) > max_length:
        shortened = title[:max_length].rstrip()
        # Try not to cut in the middle of a word.
        if " " in shortened:
            shortened = shortened.rsplit(" ", 1)[0]
        title = shortened.rstrip(" .-_")

    return title


def unique_destination(directory: Path, stem: str, current_path: Path) -> Path:
    """Return a collision-free destination path."""
    candidate = directory / f"{stem}.pdf"

    # Case-insensitive same-name check for portability.
    if candidate.name.lower() == current_path.name.lower():
        return current_path

    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}).pdf"
        counter += 1

    return candidate


def extract_title(pdf_path: Path):
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        return None, f"Could not open PDF: {exc}"

    try:
        title = title_from_metadata(doc, pdf_path.stem)
        source = "metadata"

        if not title:
            title = title_from_first_page(doc)
            source = "first page"

        if not title:
            return None, "No reliable title found"

        title = clean_title(title)

        if len(title) < 5:
            return None, "Detected title was too short"

        return title, source

    except Exception as exc:
        return None, f"Title detection failed: {exc}"

    finally:
        doc.close()


def iter_pdfs(directory: Path, recursive: bool):
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(
        (p for p in directory.glob(pattern) if p.is_file()),
        key=lambda p: str(p).lower(),
    )


def rename_pdfs(directory: Path, recursive: bool = False, dry_run: bool = False):
    pdfs = iter_pdfs(directory, recursive)

    if not pdfs:
        print(f"No PDF files found in: {directory}")
        return

    renamed = 0
    skipped = 0
    failed = 0

    print(f"Found {len(pdfs)} PDF file(s).\n")

    for pdf_path in pdfs:
        title, info = extract_title(pdf_path)

        if not title:
            print(f"[SKIP]   {pdf_path.name}")
            print(f"         {info}\n")
            skipped += 1
            continue

        destination = unique_destination(pdf_path.parent, title, pdf_path)

        if destination == pdf_path:
            print(f"[OK]     {pdf_path.name}")
            print("         Already correctly named\n")
            skipped += 1
            continue

        print(f"[RENAME] {pdf_path.name}")
        print(f"      -> {destination.name}")
        print(f"         title source: {info}")

        if dry_run:
            print("         DRY RUN: no change made\n")
            renamed += 1
            continue

        try:
            pdf_path.rename(destination)
            print("         Done\n")
            renamed += 1
        except Exception as exc:
            print(f"         ERROR: {exc}\n")
            failed += 1

    print("=" * 60)
    if dry_run:
        print(f"Would rename: {renamed}")
    else:
        print(f"Renamed:      {renamed}")
    print(f"Skipped:      {skipped}")
    print(f"Failed:       {failed}")


def main():
    parser = argparse.ArgumentParser(
        description="Rename academic PDFs using titles detected inside the PDF."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing PDFs. Default: current directory",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Also process PDFs inside subdirectories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without actually renaming files",
    )

    args = parser.parse_args()

    directory = Path(args.directory).expanduser().resolve()

    if not directory.exists():
        print(f"ERROR: Directory does not exist: {directory}")
        sys.exit(1)

    if not directory.is_dir():
        print(f"ERROR: Not a directory: {directory}")
        sys.exit(1)

    rename_pdfs(
        directory=directory,
        recursive=args.recursive,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
