// Shared helpers for the browser end-to-end checks. They drive a real Chrome against a running stack
// (docker compose up, or any hosted copy) and talk to the API directly to set up and verify data.
//
//   BASE_URL  the UI,  default http://localhost:8080
//   API_URL   the API, default http://localhost:8000/api/v1
//   CHROME_PATH  a Chrome or Chromium binary (looked for in the usual places when unset)

import { existsSync } from "node:fs";
import puppeteer from "puppeteer-core";

export const BASE_URL = (process.env.BASE_URL ?? "http://localhost:8080").replace(/\/+$/, "");
export const API_URL = (process.env.API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
];

export function launch() {
  const executablePath = CHROME_CANDIDATES.find((path) => path && existsSync(path));
  if (!executablePath) {
    throw new Error("No Chrome found. Set CHROME_PATH to a Chrome or Chromium binary.");
  }
  return puppeteer.launch({ executablePath, headless: true, args: ["--no-sandbox"] });
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let failures = 0;
let total = 0;

export function check(name, ok, detail = "") {
  total += 1;
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : `  -> ${detail}`}`);
}

export function finish() {
  console.log(`\n${total - failures}/${total} passed`);
  process.exit(failures === 0 ? 0 : 1);
}

/** A call to the API as a test client, with the test clock set. */
export function apiClient(clock) {
  return async (method, path, body) => {
    const response = await fetch(API_URL + path, {
      method,
      headers: { "Content-Type": "application/json", "X-Test-Clock": clock },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    return [response.status, text ? JSON.parse(text) : null];
  };
}

/** The clock the checks run on: 09:00 India time on the seed anchor day, so seeded strikes count. */
export async function seedClock() {
  const response = await fetch(`${API_URL}/clock`);
  const info = await response.json();
  return {
    clock: `${info.seed_anchor_date}T09:00:00+05:30`,
    anchor: info.seed_anchor_date,
    testClockEnabled: info.test_clock_enabled,
  };
}

export function addDays(isoDate, days) {
  const moment = new Date(`${isoDate}T00:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + days);
  return moment.toISOString().slice(0, 10);
}

/** A page whose local storage already holds the test clock, so every request carries it. */
export async function openPage(browser, clock, width = 1280, height = 900) {
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  const problems = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("status of 4")) {
      problems.push(message.text().slice(0, 160));
    }
  });
  page.on("pageerror", (error) => problems.push(String(error).slice(0, 160)));
  page.problems = problems;
  await page.evaluateOnNewDocument(
    (value) => localStorage.setItem("clinic.testClock", value),
    clock,
  );
  return page;
}

export async function clickButton(page, label) {
  return page.evaluate((text) => {
    const button = [...document.querySelectorAll("button")].find(
      (candidate) => candidate.innerText.trim().startsWith(text) && !candidate.disabled,
    );
    if (!button) return false;
    button.click();
    return true;
  }, label);
}

export async function buttonDisabled(page, label) {
  return page.evaluate((text) => {
    const button = [...document.querySelectorAll("button")].find(
      (candidate) => candidate.innerText.trim() === text,
    );
    return button ? button.disabled : null;
  }, label);
}

/** Choose an option of the <select> inside the label with this text, the way a person would. */
export async function chooseOption(page, labelText, value) {
  return page.evaluate(
    (label, wanted) => {
      const field = [...document.querySelectorAll("label")].find((candidate) =>
        candidate.innerText.trim().startsWith(label),
      );
      const select = field?.querySelector("select");
      if (!select) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
      setter.call(select, wanted);
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    },
    labelText,
    String(value),
  );
}

/** Set a text or date field the way React notices (a plain `.value =` would be ignored). */
export async function setField(page, selector, value) {
  await page.evaluate(
    (css, wanted) => {
      const input = document.querySelector(css);
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, wanted);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    },
    selector,
    value,
  );
}
