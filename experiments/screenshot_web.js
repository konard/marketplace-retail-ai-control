// Screenshots of every screen of the web app for docs/screenshots.
// Run the demo first:
//   retail-ai-control --config pilot.toml demo
//   retail-ai-control --config pilot.toml serve --port 8765 --user 1
// then run this function with the Playwright MCP tool browser_run_code_unsafe
// (filename: experiments/screenshot_web.js) from the repository root.
async (page) => {
  const base = "http://127.0.0.1:8765";
  const out = "docs/screenshots/";
  const shots = [
    ["web-home.png", "/"],
    ["web-card.png", "/deviations/1"],
    ["web-card-retry.png", "/deviations/4"],
    ["web-journal.png", "/decisions"],
    ["web-team.png", "/team"],
    ["web-scorecard.png", "/scorecard"],
  ];
  await page.setViewportSize({ width: 1280, height: 800 });
  for (const [file, path] of shots) {
    await page.goto(base + path);
    await page.screenshot({ path: out + file, fullPage: true });
  }
  // A rejection without a reason: the error summary and the open disclosure.
  await page.goto(base + "/deviations/1");
  await page.getByText("Отклонить…").click();
  await page.getByRole("button", { name: "Отклонить", exact: true }).click();
  await page.waitForSelector(".error-summary");
  await page.screenshot({ path: out + "web-card-error.png", fullPage: true });
  // The card on a phone: one column, the decision panel after the analysis.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + "/deviations/1");
  await page.screenshot({ path: out + "web-card-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1280, height: 800 });
  return shots.length + 2;
}
