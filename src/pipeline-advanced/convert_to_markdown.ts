import fs from "fs/promises";
import path from "path";
import { spawnSync } from "child_process";
import mammoth from "mammoth";

async function main(argv: string[]): Promise<number> {
  const args = argv.slice(2);
  if (args.length !== 1) {
    console.error("Usage: ts-node src/pipeline-advanced/convert_to_markdown.ts <fichier_entree.docx>");
    return 2;
  }

  const inputPath = path.resolve(args[0]);
  // Étape 1: DOCX -> HTML (via Mammoth)
  const { value: html } = await mammoth.convertToHtml({ path: inputPath });
  const htmlOutPath = inputPath + ".html";
  await fs.writeFile(htmlOutPath, html, "utf8");
  console.log(htmlOutPath);

  // Étape 2: HTML -> Markdown (via BeautifulSoup, script Python)
  const pyScriptPath = path.join(__dirname, "html_to_markdown.py");
  const result = spawnSync("python3", [pyScriptPath, htmlOutPath], {
    stdio: "inherit",
  });
  if (result.status !== 0) {
    console.error("Erreur: la conversion HTML -> Markdown via BeautifulSoup a échoué.");
    return result.status ?? 1;
  }

  return 0;
}

main(process.argv).then(
  (code) => process.exit(code),
  (err) => {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
);
