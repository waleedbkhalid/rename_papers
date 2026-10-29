# PDF Paper Renaming Tool

This tool renames PDF research papers based on the title detected inside each PDF.

## Requirements

Install Python 3 and PyMuPDF:

```bash
pip install pymupdf
```

## Basic Usage

Run the script and give it the folder containing your PDFs:

```bash
python rename_pdfs_by_title.py ~/Downloads/papers
```

The script will:

- Find all `.pdf` files in the directory
- Try to read the paper title from PDF metadata
- If metadata is missing or unreliable, detect the title from the first page
- Clean the title so it is safe to use as a filename
- Rename the PDF
- Avoid overwriting files if two papers have the same title

## Recommended: Preview First

Before actually renaming anything, use `--dry-run`:

```bash
python rename_pdfs_by_title.py ~/Downloads/papers --dry-run
```

This shows the proposed changes without modifying any files.

Example:

```text
[RENAME] 2403.12345.pdf
      -> Decentralized Multi-Robot Path Planning with Graph Neural Networks.pdf
         title source: first page
         DRY RUN: no change made
```

If the proposed names look correct, run the command again without `--dry-run`.

## Process the Current Directory

If the script is inside the same directory as your PDFs:

```bash
python rename_pdfs_by_title.py .
```

Or preview first:

```bash
python rename_pdfs_by_title.py . --dry-run
```

## Process Subdirectories

To also rename PDFs inside subfolders:

```bash
python rename_pdfs_by_title.py ~/papers --recursive
```

Short form:

```bash
python rename_pdfs_by_title.py ~/papers -r
```

You can combine this with dry-run:

```bash
python rename_pdfs_by_title.py ~/papers --recursive --dry-run
```

## Example Workflow

```bash
cd ~/Downloads/papers

python rename_pdfs_by_title.py . --dry-run

python rename_pdfs_by_title.py .
```

## Notes

- The tool is designed primarily for academic and research papers.
- PDF metadata is used when it contains a reasonable title.
- Otherwise, the first page is analyzed and large text near the top is used to infer the title.
- If a reliable title cannot be found, the PDF is skipped.
- Existing files are never intentionally overwritten.
- Duplicate titles are renamed using names such as:

```text
Paper Title.pdf
Paper Title (2).pdf
Paper Title (3).pdf
```

## Help

To see the available command-line options:

```bash
python rename_pdfs_by_title.py --help
```
