// Individual accounts and roles in a real browser. Run it against a stack started with both
// secrets set:
//
//   AUTH_SECRET="a-long-random-signing-secret" STAFF_PASSWORD="clinic-secret-1" \
//     docker compose up -d --build backend
//   STAFF_PASSWORD="clinic-secret-1" npm run e2e:roles
//
// It signs in with the shared password (an administrator) to create a receptionist, then checks
// what each of them sees. It is not part of `npm run e2e` because the ordinary stack has no login.

import { BASE_URL, API_URL, check, finish, launch, openPage, seedClock } from "./lib.mjs";

const shared = process.env.STAFF_PASSWORD;
if (!shared) {
  console.error("Set STAFF_PASSWORD to the shared password the server was started with.");
  process.exit(2);
}
const status = await (await fetch(`${API_URL}/auth/status`)).json();
if (!status.required || !status.accounts) {
  console.error("Start the server with AUTH_SECRET and STAFF_PASSWORD set.");
  process.exit(2);
}

const { clock } = await seedClock();
const tag = String(Math.floor(Math.random() * 9000) + 1000);
const username = `reception${tag}`;
const password = "reception-pass-1";

async function api(method, path, body, token) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return [response.status, await response.json().catch(() => null)];
}

const [, boot] = await api("POST", "/auth/login", { name: "Bootstrap", password: shared });
const adminToken = boot.token;
const [created] = await api(
  "POST",
  "/staff",
  { username, display_name: `Reception ${tag}`, password, role: "RECEPTIONIST" },
  adminToken,
);
check("an administrator can create a receptionist account", created === 201, String(created));

const text = (page) => page.evaluate(() => document.body.innerText);
const links = (page) =>
  page.evaluate(() => [...document.querySelectorAll("nav a")].map((a) => a.innerText));

async function signIn(page, name, pass) {
  await page.goto(`${BASE_URL}/day`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('form[aria-label="Staff sign-in"]', { timeout: 20000 });
  await page.type('input[autocomplete="username"]', name);
  await page.type('input[type="password"]', pass);
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => document.body.innerText.includes("Day view"), {
    timeout: 20000,
  });
}

const browser = await launch();
try {
  const page = await openPage(browser, clock);
  await signIn(page, username, password);
  const nav = await links(page);
  check(
    "a receptionist does not see the Proof or Staff pages in the menu",
    !nav.some((l) => /Proof|Staff/.test(l)) && nav.some((l) => l.startsWith("Book")),
    nav.join(" | "),
  );

  await page.goto(`${BASE_URL}/admin`, { waitUntil: "domcontentloaded" });
  await page
    .waitForFunction(() => document.body.innerText.includes("is for an administrator"), {
      timeout: 20000,
    })
    .catch(() => undefined);
  check(
    "the set-up page tells a receptionist it is for an administrator",
    (await text(page)).includes("is for an administrator"),
  );

  const [, mine] = await api("POST", "/auth/login", { name: username, password });
  const [forbidden] = await api("GET", "/staff", undefined, mine.token);
  check(
    "the API refuses a receptionist the staff list (403)",
    forbidden === 403,
    String(forbidden),
  );

  await page.evaluate(() => sessionStorage.clear());
  const admin = await openPage(browser, clock);
  await signIn(admin, "Bootstrap", shared);
  const adminNav = await links(admin);
  check(
    "an administrator sees the Staff page in the menu",
    adminNav.some((l) => l.startsWith("Staff")),
    adminNav.join(" | "),
  );
  await admin.goto(`${BASE_URL}/staff`, { waitUntil: "domcontentloaded" });
  await admin
    .waitForFunction((u) => document.body.innerText.includes(u), { timeout: 20000 }, username)
    .catch(() => undefined);
  check("the Staff page lists the new account", (await text(admin)).includes(username));

  const [, listed] = await api("GET", "/staff", undefined, adminToken);
  const mineRow = listed.find((a) => a.username === username);
  await api("PATCH", `/staff/${mineRow.id}`, { active: false }, adminToken);
  const [after] = await api("GET", "/doctors", undefined, mine.token);
  check("switching an account off stops its token at once", after === 401, String(after));
  check(
    "no console errors",
    page.problems.length === 0 && admin.problems.length === 0,
    [...page.problems, ...admin.problems].join(" | "),
  );
} finally {
  await browser.close();
}
finish();
