// Screenshots every Mermaid diagram of the built docs to check that it renders
// and reads well. Serve `_site` first: `python3 -m http.server 8766 -d _site`,
// then run this with Playwright's `browser_run_code`.
async (page) => {
  const pages = ["architecture/README.html", "concept/README.html"];
  const result = [];
  await page.setViewportSize({ width: 1100, height: 800 });
  for (const path of pages) {
    await page.goto("http://127.0.0.1:8766/" + path);
    await page.waitForTimeout(4000);
    const nodes = await page.$$("pre.mermaid");
    const name = path.split("/")[0];
    for (let i = 0; i < nodes.length; i++) {
      await nodes[i].scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await nodes[i].screenshot({ path: `experiments/diagrams/${name}-${i}.png` });
      const failed = await nodes[i].evaluate(
        (n) => !n.querySelector("svg") || n.textContent.includes("Syntax error"),
      );
      result.push(`${name}-${i}: ${failed ? "FAILED" : "ok"}`);
    }
  }
  return result.join("\n");
}
