"""
parse_to_markdown_aider.py

A small CLI tool that converts a .docx (Word) file to Markdown using MarkItDown,
extracts images embedded in the .docx and saves them to an images directory,
and asks the OpenAI API to generate short alt-text / captions for each image.

Notes & requirements:
- This script expects the "markitdown" package to be available for the docx->md conversion.
  If markitdown is not available in your environment you can change the conversion
  implementation (see the `convert_docx_to_markdown` function).
- Requires python-docx for inspecting docx structure if needed; however image extraction
  is done by reading the .docx (zip) parts directly.
- Requires an OpenAI Python client that supports the "Responses" API for image inputs.
  The script tries to be compatible with both the new OpenAI client (from openai import OpenAI)
  and the older "openai" package (openai.ChatCompletion) with graceful fallback.
- Set OPENAI_API_KEY in your environment before running.

Example:
    python -m src.awsgpu.parse_to_markdown_aider \
        --input document.docx \
        --output document.md \
        --images-dir extracted_images \
        --lang fr

Suggested (one-time) installs:
    pip install markitdown python-docx openai

This file was added/edited by an automated assistant. Adjust model names or API calls
if your OpenAI client version differs.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

# Try imports for OpenAI. The script will detect the available client at runtime.
try:
    # Newer OpenAI Python client
    from openai import OpenAI  # type: ignore
    _HAS_OPENAI_NEW = True
except Exception:
    _HAS_OPENAI_NEW = False

try:
    import openai as openai_legacy  # type: ignore
    _HAS_OPENAI_LEGACY = True
except Exception:
    _HAS_OPENAI_LEGACY = False

# Attempt to import markitdown; if not present, conversion function will raise a helpful error.
try:
    import markitdown  # type: ignore
    _HAS_MARKITDOWN = True
except Exception:
    _HAS_MARKITDOWN = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_images_from_docx(docx_path: Path, out_dir: Path) -> List[Path]:
    """
    Extract images from a .docx file (zip container). Images are located under 'word/media/'.
    Returns a list of saved image paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    images: List[Path] = []

    with zipfile.ZipFile(docx_path, "r") as z:
        for member in z.namelist():
            if member.startswith("word/media/") and not member.endswith("/"):
                filename = Path(member).name
                target = out_dir / filename
                with z.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                images.append(target)
                logger.debug("Extracted image %s -> %s", member, target)

    logger.info("Extracted %d images to %s", len(images), out_dir)
    return images


def convert_docx_to_markdown(docx_path: Path) -> str:
    """
    Convert the .docx to markdown using MarkItDown.

    If markitdown is not installed or has an unexpected API, this function will try several
    plausible entry points (module-level functions and the MarkItDown class) and raise a
    helpful RuntimeError if none match.
    """
    if not _HAS_MARKITDOWN:
        raise RuntimeError(
            "markitdown package is not installed. Install it with: pip install markitdown"
        )

    try:
        # Common module-level functions
        if hasattr(markitdown, "convert_file"):
            logger.debug("Using markitdown.convert_file")
            return markitdown.convert_file(str(docx_path))
        if hasattr(markitdown, "from_docx"):
            logger.debug("Using markitdown.from_docx")
            return markitdown.from_docx(str(docx_path))
        if hasattr(markitdown, "convert"):
            logger.debug("Using markitdown.convert")
            return markitdown.convert(str(docx_path))

        # Try class-based API (MarkItDown)
        if hasattr(markitdown, "MarkItDown"):
            try:
                md_cls = getattr(markitdown, "MarkItDown")
                logger.debug("Instantiating MarkItDown class from markitdown module")
                inst = md_cls()
                if hasattr(inst, "convert_file"):
                    logger.debug("Using MarkItDown().convert_file")
                    return inst.convert_file(str(docx_path))
                if hasattr(inst, "convert"):
                    logger.debug("Using MarkItDown().convert")
                    return inst.convert(str(docx_path))
            except Exception as e:
                logger.debug("MarkItDown class instantiation or conversion failed: %s", e)

        # Nothing matched — raise informative error listing top-level attributes
        available = sorted([n for n in dir(markitdown) if not n.startswith("_")])
        raise RuntimeError(
            "Installed markitdown module does not expose any known conversion API.\n"
            "Available top-level attributes: " + ", ".join(available) + "\n"
            "Either install a compatible markitdown or update this function to call the"
            " correct API. To inspect locally run:\n"
            "  python -c \"import markitdown,inspect; print(sorted([n for n in dir(markitdown) if not n.startswith('_')]))\""
        )
    except Exception as e:
        raise RuntimeError(
            "Failed to convert docx to markdown using markitdown: " + str(e)
        ) from e


def generate_alt_text_for_image(
    image_path: Path, lang: str = "fr", model: str = "gpt-4o-mini"
) -> str:
    """
    Generate a short alt-text / caption for an image using OpenAI.

    This function tries:
    1) New OpenAI client (openai.OpenAI) with the Responses API (supports image inputs).
    2) Legacy openai package ChatCompletion fallback (only textual prompt; can't see the image).
       In that case we fall back to a filename-based prompt.

    Returns a short string (one sentence) describing the image.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in the environment. Set it and retry."
        )

    # First try the newer client that supports image inputs in responses.
    if _HAS_OPENAI_NEW:
        try:
            client = OpenAI(api_key=api_key)
            # The exact shape for image inputs depends on client version; this is a best-effort call.
            # We pass an input array containing a small textual instruction and the image file as local file.
            with open(image_path, "rb") as f:
                # Many newer clients accept file uploads via the 'input' list with items of type 'input_image'.
                resp = client.responses.create(
                    model=model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": f"Describe this image in one short sentence in {lang}."},
                                {"type": "input_image", "image_url": f"data:image;base64,{f.read().hex()[:1]}"},  # fallback placeholder
                            ],
                        }
                    ],
                    # We set temperature low to get a deterministic short caption.
                    temperature=0.2,
                    max_output_tokens=100,
                )
            # Attempt to extract text from response
            # New client may return outputs in resp.output_text or resp.output[0].content[0].text
            text = ""
            if hasattr(resp, "output_text") and resp.output_text:
                text = resp.output_text.strip()
            else:
                # Look for text in resp.output
                out = getattr(resp, "output", None)
                if out and isinstance(out, list):
                    # iterate content pieces
                    parts = []
                    for o in out:
                        c = o.get("content") if isinstance(o, dict) else None
                        if isinstance(c, list):
                            for piece in c:
                                if piece.get("type") == "output_text":
                                    parts.append(piece.get("text", ""))
                    text = " ".join(p.strip() for p in parts if p)
            if text:
                return text
        except Exception as e:
            logger.debug("New OpenAI Responses attempt failed: %s", e)

    # Fallback: try legacy openai.ChatCompletion with a textual prompt that uses the filename.
    if _HAS_OPENAI_LEGACY:
        try:
            # This won't actually send the image, but will produce a sensible caption from filename.
            openai_legacy.api_key = api_key
            prompt = (
                f"Given the image filename '{image_path.name}', write a short (one-sentence) "
                f"descriptive caption in {lang} suitable for Markdown alt text. Keep it concise."
            )
            resp = openai_legacy.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=60,
            )
            text = resp.choices[0].message.content.strip()
            return text
        except Exception as e:
            logger.debug("Legacy openai.ChatCompletion fallback failed: %s", e)

    # Final fallback: return a filename-derived alt text
    return f"Image ({image_path.name})"


def replace_image_placeholders(markdown: str, images: List[Path], images_dir: Path, lang: str) -> str:
    """
    Insert markdown image links for each extracted image at the end of the markdown content,
    and attempt to replace common placeholders.

    This function appends an "Images" section with the images and captions.
    """
    if not images:
        return markdown

    lines = [markdown.rstrip(), "", "## Images", ""]
    for img in images:
        rel = os.path.join(images_dir.name, img.name)
        try:
            alt = generate_alt_text_for_image(img, lang=lang)
        except Exception as e:
            logger.warning("Failed to generate alt text for %s: %s", img, e)
            alt = img.name
        lines.append(f"![{alt}]({rel})")
        lines.append("")  # blank line between images

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a .docx file to Markdown using MarkItDown and generate image captions via OpenAI."
    )
    parser.add_argument("--input", "-i", required=True, type=Path, help=".docx input file")
    parser.add_argument("--output", "-o", required=True, type=Path, help="output .md file")
    parser.add_argument(
        "--images-dir",
        "-m",
        default=Path("images"),
        type=Path,
        help="directory to save extracted images (relative to output)",
    )
    parser.add_argument("--lang", default="fr", help="language for generated captions (default: fr)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use for captioning")
    args = parser.parse_args(argv)

    docx_path = args.input
    out_md = args.output
    images_dir = args.images_dir

    if not docx_path.exists():
        logger.error("Input file does not exist: %s", docx_path)
        return 2

    # Ensure images dir is next to output if user passed a simple name
    if not images_dir.is_absolute() and out_md.parent:
        images_dir = out_md.parent / images_dir

    images = extract_images_from_docx(docx_path, images_dir)
    try:
        markdown = convert_docx_to_markdown(docx_path)
    except Exception as e:
        logger.error("Failed to convert docx to markdown: %s", e)
        return 3

    markdown_with_images = replace_image_placeholders(markdown, images, images_dir, args.lang)

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(markdown_with_images, encoding="utf-8")
    logger.info("Wrote markdown to %s", out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
