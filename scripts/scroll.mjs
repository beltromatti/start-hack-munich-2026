// Scroll through a page like a visitor and save one viewport screenshot per step.
// Usage: node scroll.mjs <name> <url> [maxTiles]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const [name, url, maxArg] = process.argv.slice(2);
const maxTiles = Number(maxArg || 14);
const out = new URL("../scroll/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--hide-scrollbars", "--mute-audio", "--no-first-run"],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
});
try {
  const page = await browser.newPage();
  await page.setUserAgent(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
  );
  await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 2500));
  // close common cookie banners
  await page
    .evaluate(() => {
      const words = ["accept", "akzeptieren", "agree", "allow all", "got it", "alle akzeptieren", "accept all"];
      for (const el of document.querySelectorAll("button, a[role=button], [role=button]")) {
        const t = (el.textContent || "").trim().toLowerCase();
        if (t.length < 30 && words.some((w) => t === w || t.startsWith(w))) {
          el.click();
          break;
        }
      }
    })
    .catch(() => {});
  await new Promise((r) => setTimeout(r, 600));
  let i = 0;
  let lastY = -1;
  while (i < maxTiles) {
    const file = `${out}${name}-${String(i).padStart(2, "0")}.jpg`;
    await page.screenshot({ path: file, type: "jpeg", quality: 72 });
    i += 1;
    await page.evaluate(() => window.scrollBy({ top: 780, behavior: "instant" }));
    await new Promise((r) => setTimeout(r, 1100));
    const y = await page.evaluate(() => Math.round(window.scrollY));
    if (y === lastY) break;
    lastY = y;
  }
  console.log(`ok ${name} ${i} tiles`);
} catch (e) {
  console.log(`FAIL ${name} ${String(e).slice(0, 120)}`);
} finally {
  await browser.close();
}
