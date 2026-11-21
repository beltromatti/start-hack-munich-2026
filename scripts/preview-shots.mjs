// Screenshots of the local dashboard preview. Usage: node preview-shots.mjs <outDir> [width]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const out = process.argv[2];
const width = Number(process.argv[3] || 1440);
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--hide-scrollbars", "--no-first-run"],
  defaultViewport: { width, height: width < 700 ? 844 : 1000, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
await page.goto("http://127.0.0.1:8791/", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise((r) => setTimeout(r, 2500));
const tag = width < 700 ? "m" : "d";
await page.screenshot({ path: `${out}/${tag}-1-requests.jpg`, type: "jpeg", quality: 80, fullPage: true });
await page.click('button[data-tab="threads"]');
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: `${out}/${tag}-2-threads-latest.jpg`, type: "jpeg", quality: 80, fullPage: true });
// open the oldest request (round 1) and expand its first two carrier rows
const deals = await page.$$(".deal");
if (deals.length) await deals[deals.length - 1].click();
await new Promise((r) => setTimeout(r, 2500));
const bids = await page.$$("details.bid > summary");
for (const b of bids.slice(0, 1)) await b.click();
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: `${out}/${tag}-3-thread-round1.jpg`, type: "jpeg", quality: 80, fullPage: true });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
console.log(JSON.stringify({ width, deals: deals.length, bids: bids.length, horizontalOverflowPx: overflow, errors }));
await browser.close();
