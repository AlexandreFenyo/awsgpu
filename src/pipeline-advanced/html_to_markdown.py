#!/usr/bin/env python3
"""
Convertit un fichier HTML en Markdown en utilisant BeautifulSoup.
Usage: python3 src/pipeline-advanced/html_to_markdown.py <chemin_html>
Produit un fichier <chemin_html>.md et affiche son nom.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple, Union

from bs4 import BeautifulSoup, NavigableString, Tag  # type: ignore[import-not-found]

print("Démarrage de html_to_markdown.py")

InlineNode = Union[NavigableString, Tag]


def _get_text_inline(node: InlineNode) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    name = node.name.lower()

    if name in ("strong", "b"):
        return f"**{''.join(_get_text_inline(c) for c in node.children)}**"
    if name in ("em", "i"):
        return f"*{''.join(_get_text_inline(c) for c in node.children)}*"
    if name == "code":
        # Si 'code' est dans 'pre', le bloc parent s'en charge.
        return f"`{''.join(_get_text_inline(c) for c in node.children)}`"
    if name == "a":
        text = ''.join(_get_text_inline(c) for c in node.children).strip() or node.get("href", "")
        href = node.get("href", "")
        return f"[{text}]({href})" if href else text
    if name == "img":
        alt = node.get("alt", "").strip()
        src = node.get("src", "").strip()
        return f"![{alt}]({src})" if src else ""
    if name == "br":
        return "  \n"

    # Par défaut: concaténer le contenu inline
    return ''.join(_get_text_inline(c) for c in node.children)


def _render_list(items: List[Tag], ordered: bool, indent: int = 0, start: int = 1) -> str:
    lines: List[str] = []
    current = start
    for li in items:
        # Déterminer le marqueur de l'élément courant
        if ordered:
            num = current
            val_attr = li.get("value")
            if isinstance(val_attr, str) and val_attr.strip().isdigit():
                num = int(val_attr.strip())
                current = num + 1
            else:
                current += 1
            marker = f"{num}. "
        else:
            marker = "- "

        # Séparer le contenu inline et les sous-listes
        sublines: List[str] = []
        buf_inline: List[str] = []

        for child in li.children:
            if isinstance(child, NavigableString):
                buf_inline.append(str(child))
                continue
            if isinstance(child, Tag):
                if child.name in ("ul", "ol"):
                    # Vider le tampon inline une fois avant la sous-liste
                    text = ''.join(buf_inline).strip()
                    if text:
                        sublines.append((" " * indent) + marker + text)
                        marker = "  "  # indentation pour les lignes suivantes
                    # Rendu de la sous-liste avec gestion de start/value
                    nested_items = child.find_all("li", recursive=False)
                    nested_start = 1
                    if child.name == "ol":
                        start_attr = child.get("start")
                        if isinstance(start_attr, str) and start_attr.strip().isdigit():
                            nested_start = int(start_attr.strip())
                    nested = _render_list(
                        nested_items,
                        ordered=(child.name == "ol"),
                        indent=indent + 2,
                        start=nested_start,
                    )
                    for ln in nested.splitlines():
                        sublines.append((" " * (indent + 2)) + ln)
                    buf_inline = []
                else:
                    buf_inline.append(_get_text_inline(child))

        # Vider le reste du tampon inline
        text = ''.join(buf_inline).strip()
        if text:
            sublines.append((" " * indent) + marker + text)
        if not sublines:
            sublines.append((" " * indent) + marker + "")
        lines.extend(sublines)
    return "\n".join(lines)


def _table_to_markdown(table: Tag) -> str:
    # Récupérer lignes
    rows = table.find_all("tr")
    if not rows:
        return ""

    def _cells_text(tr: Tag) -> List[str]:
        cells = tr.find_all(["th", "td"])
        texts: List[str] = []
        for c in cells:
            texts.append(' '.join(''.join(_get_text_inline(ch) for ch in c.children).split()))
        return texts

    header_cells = None
    # Chercher en priorité <thead>, sinon la première ligne avec <th>, sinon la 1ère ligne
    thead = table.find("thead")
    if thead:
        head_trs = thead.find_all("tr")
        if head_trs:
            header_cells = _cells_text(head_trs[0])
    if header_cells is None:
        for r in rows:
            if r.find("th"):
                header_cells = _cells_text(r)
                break
    body_rows = rows
    if header_cells is None and rows:
        # Utiliser la première ligne comme en-tête par défaut
        header_cells = _cells_text(rows[0])
        body_rows = rows[1:]

    # Construire Markdown
    out: List[str] = []
    if header_cells:
        out.append("| " + " | ".join(header_cells) + " |")
        out.append("| " + " | ".join(["---"] * len(header_cells)) + " |")
    for r in body_rows:
        cells = _cells_text(r)
        if cells:
            out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _block_to_markdown(node: Tag, heading_counters: List[int]) -> str:
    name = node.name.lower()
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        text = ''.join(_get_text_inline(c) for c in node.children).strip()
        # Numérotation automatique des titres (style Word)
        idx = level - 1
        heading_counters[idx] += 1
        for j in range(idx + 1, 6):
            heading_counters[j] = 0
        numbering = ".".join(str(n) for n in heading_counters[:level] if n > 0)
        prefix = f"{numbering} " if numbering else ""
        return f"{'#' * level} {prefix}{text}\n"
    if name == "p":
        text = ''.join(_get_text_inline(c) for c in node.children).strip()
        return (text + "\n") if text else ""
    if name == "pre":
        # Capturer le code brut
        code = node.get_text()
        return f"```\n{code.rstrip()}\n```\n"
    if name == "blockquote":
        raw = ''.join(_get_text_inline(c) for c in node.children)
        lines = [f"> {ln}".rstrip() for ln in raw.splitlines()]
        return "\n".join(lines) + "\n"
    if name == "ul":
        items = node.find_all("li", recursive=False)
        return _render_list(items, ordered=False) + "\n"
    if name == "ol":
        items = node.find_all("li", recursive=False)
        start = 1
        start_attr = node.get("start")
        if isinstance(start_attr, str) and start_attr.strip().isdigit():
            start = int(start_attr.strip())
        return _render_list(items, ordered=True, start=start) + "\n"
    if name == "hr":
        return "---\n"
    if name == "table":
        tbl = _table_to_markdown(node)
        return (tbl + "\n") if tbl else ""
    # Par défaut: texte brut du bloc
    return node.get_text().strip() + ("\n" if node.get_text().strip() else "")


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    parts: List[str] = []
    heading_counters: List[int] = [0, 0, 0, 0, 0, 0]
    for child in body.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                parts.append(text + "\n")
            continue
        if isinstance(child, Tag):
            parts.append(_block_to_markdown(child, heading_counters))
    # Insérer des lignes blanches entre blocs
    md = ""
    for chunk in parts:
        if not chunk:
            continue
        if not md.endswith("\n\n") and not md.endswith("\n") and not chunk.startswith("\n"):
            md += "\n"
        md += chunk
        if not md.endswith("\n\n"):
            md += "\n"
    # Nettoyage simple des espaces superflus
    lines = [ln.rstrip() for ln in md.splitlines()]
    # Supprimer triples lignes vides consécutives
    compact: List[str] = []
    empty_count = 0
    for ln in lines:
        if ln.strip() == "":
            empty_count += 1
            if empty_count <= 2:
                compact.append("")
        else:
            empty_count = 0
            compact.append(ln)
    return "\n".join(compact).strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python3 src/pipeline-advanced/html_to_markdown.py <fichier.html>", file=sys.stderr)
        return 2
    html_path = Path(argv[1]).resolve()
    if not html_path.exists():
        print(f"Fichier introuvable: {html_path}", file=sys.stderr)
        return 1
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    md = html_to_markdown(html)
    out_path = html_path.with_name(html_path.name + ".md")
    out_path.write_text(md, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
