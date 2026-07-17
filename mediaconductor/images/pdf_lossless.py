#!/usr/bin/env python3
"""mediaconductor.images.pdf_lossless — shim for the mediaconductor to-pdf-lossless CLI entry point."""

from mediaconductor.config import load_download_config
from mediaconductor.images.pdf import images_to_pdf
from mediaconductor.paths import chapter_dir


def main() -> None:
    dl      = load_download_config()
    name    = dl["name"]
    chapter = int(dl["chapter"])
    ch_dir  = chapter_dir(name, chapter)
    images_to_pdf(ch_dir / "panels_filename", ch_dir / f"chapter_{chapter:02d}_lossless.pdf", lossless=True)


if __name__ == "__main__":
    main()
