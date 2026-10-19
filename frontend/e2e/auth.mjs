// Sign-in flow in a real browser. Run it against a stack started with STAFF_PASSWORD set:
//
//   STAFF_PASSWORD="clinic-secret-1" docker compose up -d --build backend
//   STAFF_PASSWORD="clinic-secret-1" npm run e2e:auth
//
// It is not part of `npm run e2e` because the ordinary stack has no login.

import { BASE_URL, API_URL, check, finish, launch, openPage, seedClock, sleep } from "./lib.mjs";

const password = process.env.STAFF_PASSWORD;
if (!password) {
  console.error("Set STAFF_PASSWORD to the password the server was started with.");
  process.exit(2);
}

const { clock } = await seedClock();
const status = await (await fetch(`${API_URL}/auth/status`)).json();
if (!status.required) {
  console.error("This server has no staff login; start it with STAFF_PASSWORD set.");
  process.exit(2);
}

const text = (page) => page.evaluate(() => document.body.innerText);
// the signed-in person is named on the menu in the top bar
const whoIs = (page) =>
  page.evaluate(() => document.querySelector(".user-menu summary")?.innerText ?? "");
const browser = await launch();
try {
  const open = await fetch(`${API_URL}/doctors`);
  check("the API refuses a caller without a token", open.status === 401, String(open.status));

  const page = await openPage(browser, clock);
  await page.goto(`${BASE_URL}/day`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('form[aria-label="Staff sign-in"]', { timeout: 20000 });
  check(
    "an unsigned visitor sees the sign-in form, not the app",
    !(await text(page)).includes("Day view"),
  );

  await page.type('input[autocomplete="username"]', "Meera");
  await page.type('input[type="password"]', "not-the-password");
  await page.click('button[type="submit"]');
  await page
    .waitForFunction(() => document.body.innerText.includes("password is not correct"), {
      timeout: 20000,
    })
    .catch(() => undefined);
  check(
    "a wrong password says so and stays on the form",
    (await text(page)).includes("password is not correct"),
  );

  await page.focus('input[type="password"]');
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyA");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await page.type('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => document.body.innerText.includes("Day view"), {
    timeout: 20000,
  });
  check("the right password opens the app", (await whoIs(page)).includes("Meera"));

  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .waitForFunction(
      () => document.querySelector(".user-menu summary")?.innerText.includes("Meera"),
      {
        timeout: 20000,
      },
    )
    .catch(() => undefined);
  check("a reload keeps the person signed in", (await whoIs(page)).includes("Meera"));

  // a token the server no longer accepts brings the form back instead of a page of errors
  await page.evaluate(() => {
    const session = JSON.parse(sessionStorage.getItem("clinic.staffToken"));
    sessionStorage.setItem(
      "clinic.staffToken",
      JSON.stringify({ ...session, token: "forged.token" }),
    );
  });
  await page.goto(`${BASE_URL}/queue`, { waitUntil: "domcontentloaded" });
  await page
    .waitForSelector('form[aria-label="Staff sign-in"]', { timeout: 30000 })
    .catch(() => undefined);
  check(
    "a rejected token returns to the sign-in form",
    (await text(page)).includes("Staff password"),
  );

  await page.type('input[autocomplete="username"]', "Ravi");
  await page.type('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForFunction(
    () => document.querySelector(".user-menu summary")?.innerText.includes("Ravi"),
    {
      timeout: 20000,
    },
  );
  await page.evaluate(() =>
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent.trim().startsWith("Sign out"))
      .click(),
  );
  await page
    .waitForSelector('form[aria-label="Staff sign-in"]', { timeout: 20000 })
    .catch(() => undefined);
  check("signing out returns to the sign-in form", (await text(page)).includes("Staff password"));
  await sleep(200);
  check("no console errors during sign-in", page.problems.length === 0, page.problems.join(" | "));
} finally {
  await browser.close();
}
finish();
