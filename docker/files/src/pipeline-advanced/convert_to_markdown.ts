import fs from "fs/promises";
import path from "path";
import { spawnSync } from "child_process";
import mammoth from "mammoth";
import { parse } from "node-html-parser";

 // ts-node ./src/pipeline-advanced/convert_to_markdown.ts /mnt/c/Temp/CCTP.docx

function stripTableOfContents(html: string): string {
  const root = parse(html);

  // Supprime conteneurs évidents (classes toc/table-of-contents)
  root.querySelectorAll("div,section,nav").forEach((el) => {
    const cls = el.getAttribute("class") || "";
    if (/\b(toc|table-of-contents)\b/i.test(cls)) {
      el.remove();
    }
  });

  // Heuristique: paragraphes Word avec classes MsoToc*, ou classes 'toc'
  root.querySelectorAll("p").forEach((el) => {
    const cls = el.getAttribute("class") || "";
    const anchors = el.querySelectorAll("a[href]");
    const onlyTocLinks =
      anchors.length > 0 &&
      anchors.every((a) => /^#_?Toc/i.test(a.getAttribute("href") || ""));
    if (/\b(MsoToc\d*|toc|table-of-contents)\b/i.test(cls) || onlyTocLinks) {
      el.remove();
    }
  });

  // Listes qui ne pointent que vers des ancres _Toc... => table des matières
  root.querySelectorAll("ol,ul").forEach((el) => {
    const anchors = el.querySelectorAll("a[href]");
    if (
      anchors.length > 0 &&
      anchors.every((a) => /^#_?Toc/i.test(a.getAttribute("href") || ""))
    ) {
      el.remove();
    }
  });

  // En-tête "Table des matières" / "Sommaire" / "Table of Contents"
  const header = root
    .querySelectorAll("h1,h2,h3,h4,h5,h6,p")
    .find((el) => {
      const text = (el.text || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, " ");
      return (
        text === "table des matières" ||
        text === "sommaire" ||
        text === "table of contents"
      );
    });
  if (header) {
    header.remove();
  }

  return root.toString();
}

async function main(argv: string[]): Promise<number> {
  const args = argv.slice(2);
  if (args.length !== 1) {
    console.error("Usage: ts-node src/pipeline-advanced/convert_to_markdown.ts <fichier_entree.docx>");
    return 2;
  }

  const inputPath = path.resolve(args[0]);
  // Étape 1: DOCX -> HTML (via Mammoth)
  const { value: html } = await mammoth.convertToHtml({ path: inputPath });
  const stripped = stripTableOfContents(html);
  const htmlOutPath = inputPath + ".html";
  await fs.writeFile(htmlOutPath, stripped, "utf8");
  console.log(htmlOutPath);
  return 0;
}

main(process.argv).then(
  (code) => process.exit(code),
  (err) => {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
);
