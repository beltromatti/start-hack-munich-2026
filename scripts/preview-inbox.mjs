import puppeteer from "puppeteer-core";
const out = process.argv[2];
const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true, args: ["--hide-scrollbars"], defaultViewport: { width: 1440, height: 900 } });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://127.0.0.1:8791/", { waitUntil: "networkidle2" });
await new Promise((r) => setTimeout(r, 2000));
await page.click('button[data-tab="inbox"]');
const rows = await page.$$(".mailrow > summary");
await rows[1].click();
await new Promise((r) => setTimeout(r, 600));
await page.screenshot({ path: out, type: "jpeg", quality: 80 });
const hasLink = await page.$(".mailrow[open] .link") !== null;
if (hasLink) { await page.click(".mailrow[open] .link"); await new Promise((r) => setTimeout(r, 1500)); }
const tab = await page.evaluate(() => document.querySelector(".tabs button.active")?.dataset.tab);
console.log(JSON.stringify({ rows: rows.length, hasLink, tabAfterLink: tab, errors }));
await browser.close();
