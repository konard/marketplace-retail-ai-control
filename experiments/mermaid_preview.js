// Renders Mermaid sources with the same Mermaid version and theme as the docs
// and screenshots each one into experiments/diagrams/preview-N.png. Used to
// try layouts quickly: `python experiments/mermaid_preview.py *.mmd` fills
// DIAGRAMS and writes experiments/diagrams/_preview_run.js to run with
// Playwright's `browser_run_code`.
async (page) => {
  const DIAGRAMS = globalThis.DIAGRAMS || [];
  const html = `<!doctype html><html><body style="font-family:sans-serif;width:1000px">
    ${DIAGRAMS.map((d, i) => `<pre class="mermaid" id="d${i}">${d.replace(/</g, "&lt;")}</pre>`).join("")}
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: false, theme: "neutral" });
      await mermaid.run();
      document.body.dataset.done = "1";
    </script></body></html>`;
  await page.setViewportSize({ width: 1100, height: 800 });
  await page.setContent(html);
  await page.waitForSelector("body[data-done]", { timeout: 20000 });
  const out = [];
  for (let i = 0; i < DIAGRAMS.length; i++) {
    const el = await page.$(`#d${i}`);
    await el.screenshot({ path: `experiments/diagrams/preview-${i}.png` });
    out.push(`${i}: ${(await el.textContent()).includes("Syntax error") ? "FAILED" : "ok"}`);
  }
  return out.join("\n");
}
