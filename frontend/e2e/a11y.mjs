// Automated accessibility scan (axe-core, WCAG 2.0/2.1 A and AA plus best practices) of every page,
// in the light theme (the only one), at desktop and phone width. A violation fails the run.

import axe from "axe-core";
import { BASE_URL, check, finish, launch, openPage, seedClock, sleep } from "./lib.mjs";

const { clock } = await seedClock();
const pages = [
  "/",
  "/policies",
  "/my-day",
  "/day",
  "/book?patient=1",
  "/queue",
  "/calls",
  "/patients",
  "/patients/1",
  "/admin",
  "/reports",
  "/proof",
];

// A page that reloads while it is being scanned (a late redirect) loses its frame; scan it again.
async function scan(page, path) {
  for (let attempt = 1; ; attempt++) {
    try {
      await page.goto(BASE_URL + path, { waitUntil: "domcontentloaded" });
      await sleep(2500);
      await page.evaluate(axe.source);
      return await page.evaluate(() =>
        axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] }),
      );
    } catch (error) {
      if (attempt >= 3 || !/detached|context was destroyed/i.test(String(error))) throw error;
    }
  }
}

const browser = await launch();
try {
  for (const scheme of ["light"]) {
    for (const width of [1280, 390]) {
      const page = await openPage(browser, clock, width, 900);
      await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: scheme }]);
      for (const path of pages) {
        const result = await scan(page, path);
        const summary = result.violations
          .map((v) => `${v.id} (${v.nodes.length}) e.g. ${v.nodes[0].target.join(" ")}`)
          .join("; ");
        check(
          `${scheme} ${width}px ${path}: no accessibility violations`,
          result.violations.length === 0,
          summary,
        );
      }
      await page.close();
    }
  }
} finally {
  await browser.close();
}
finish();
