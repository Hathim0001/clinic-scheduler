// End-to-end smoke test: the flows a receptionist uses, in a real browser, against a running stack.
// It creates its own doctor and patients, so it can run again and again on the same database.

import {
  addDays,
  apiClient,
  buttonDisabled,
  check,
  chooseOption,
  setField,
  clickButton,
  finish,
  launch,
  openPage,
  seedClock,
  sleep,
  BASE_URL,
} from "./lib.mjs";

const { clock, anchor, testClockEnabled } = await seedClock();
if (!testClockEnabled) {
  console.error("The test clock is switched off on this server; these checks need it.");
  process.exit(2);
}
const api = apiClient(clock);

// A doctor of our own: Monday to Friday 09:00-13:00 in 15 minute slots.
const tag = String(Math.floor(Math.random() * 9000) + 1000);
const [, doctor] = await api("POST", "/doctors", {
  name: `Dr. E2E ${tag}`,
  speciality: "General",
  slot_length_min: 15,
  daily_cap: 20,
});
const windows = [0, 1, 2, 3, 4].map((weekday) => ({ weekday, start: "09:00", end: "13:00" }));
await api("PUT", `/doctors/${doctor.id}/weekly-windows`, { windows, acknowledge_conflicts: false });

// A weekday two to four weeks ahead, different each run.
let day = addDays(anchor, 14 + Math.floor(Math.random() * 14));
while ([0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay())) day = addDays(day, 1);

async function newPatient(label) {
  const phone = "9" + String(Math.floor(Math.random() * 1e9)).padStart(9, "0");
  const [, patient] = await api("POST", "/patients", {
    name: `E2E ${label} ${phone.slice(-4)}`,
    phone,
    date_of_birth: "1992-02-02",
  });
  return patient;
}

const bookUrl = (patientId) =>
  `${BASE_URL}/book?patient=${patientId}&doctor=${doctor.id}&date=${day}`;

const browser = await launch();
try {
  // 1 booking through the form
  const booker = await newPatient("book");
  let page = await openPage(browser, clock);
  await page.goto(bookUrl(booker.id), { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".slot-list button");
  await clickButton(page, "10:00");
  await page.type("textarea", "Fever, 3 days");
  await clickButton(page, "Book the appointment");
  await page
    .waitForFunction(() => document.body.innerText.includes("Booked:"), { timeout: 20000 })
    .catch(() => undefined);
  check(
    "booking through the form shows the confirmation",
    (await page.evaluate(() => document.body.innerText)).includes("Booked:"),
  );
  const [, mine] = await api("GET", `/patients/${booker.id}/appointments`);
  check("exactly one appointment exists", mine.total === 1, String(mine.total));
  check("no console errors while booking", page.problems.length === 0, page.problems.join(" | "));

  // 2 a slot taken while the page was open gives a plain message
  const late = await newPatient("late");
  const stale = await openPage(browser, clock);
  await stale.goto(bookUrl(late.id), { waitUntil: "domcontentloaded" });
  await stale.waitForSelector(".slot-list button");
  const other = await newPatient("other");
  await api("POST", "/appointments", {
    doctor_id: doctor.id,
    patient_id: other.id,
    start_at: `${day}T10:30:00+05:30`,
    reason: "x",
  });
  await clickButton(stale, "10:30");
  await stale.type("textarea", "Cough");
  await clickButton(stale, "Book the appointment");
  await stale.waitForSelector(".banner.error", { timeout: 20000 }).catch(() => undefined);
  const message = await stale.evaluate(
    () => document.querySelector(".banner.error")?.innerText ?? "",
  );
  check(
    "a slot taken meanwhile gives a plain message",
    /taken|booked/i.test(message) && !message.includes("{"),
    message,
  );

  // 3 a triple click books once
  const clicker = await newPatient("dbl");
  const dbl = await openPage(browser, clock);
  await dbl.goto(bookUrl(clicker.id), { waitUntil: "domcontentloaded" });
  await dbl.waitForSelector(".slot-list button");
  await clickButton(dbl, "11:00");
  await dbl.type("textarea", "Rash");
  await dbl.evaluate(() => {
    const button = [...document.querySelectorAll("button")].find(
      (b) => b.innerText.trim() === "Book the appointment",
    );
    button.click();
    button.click();
    button.click();
  });
  await sleep(5000);
  const [, clicked] = await api("GET", `/patients/${clicker.id}/appointments`);
  check(
    "three quick clicks on Book create one appointment",
    clicked.total === 1,
    String(clicked.total),
  );

  // 4 the emergency warning and the deposit gate
  const urgent = await openPage(browser, clock);
  await urgent.goto(bookUrl(clicker.id), { waitUntil: "domcontentloaded" });
  await urgent.waitForSelector("textarea");
  await urgent.type("textarea", "severe chest pain and cannot breathe");
  await urgent
    .waitForFunction(() => document.body.innerText.includes("112"), { timeout: 15000 })
    .catch(() => undefined);
  check(
    "emergency symptoms show the 112 warning",
    (await urgent.evaluate(() => document.body.innerText)).includes("112"),
  );

  const flagged = await openPage(browser, clock);
  await flagged.goto(bookUrl(1), { waitUntil: "domcontentloaded" });
  await flagged.waitForSelector(".slot-list button");
  await flagged
    .waitForFunction(() => document.body.innerText.includes("Deposit required"), { timeout: 20000 })
    .catch(() => undefined);
  await clickButton(flagged, "09:15");
  await flagged.type("textarea", "Follow-up");
  const before = await buttonDisabled(flagged, "Book the appointment");
  await flagged.evaluate(() =>
    document.querySelector('input[type="checkbox"]').scrollIntoView({ block: "center" }),
  );
  await flagged.click('input[type="checkbox"]');
  const after = await buttonDisabled(flagged, "Book the appointment");
  check(
    "a flagged patient cannot book until the deposit is acknowledged",
    before === true && after === false,
    `before=${before} after=${after}`,
  );

  // 4b a visit of two slots, chosen from the length menu
  const longVisit = await newPatient("long");
  const tall = await openPage(browser, clock);
  await tall.goto(bookUrl(longVisit.id), { waitUntil: "domcontentloaded" });
  await tall.waitForSelector(".slot-list button");
  await chooseOption(tall, "Length of the visit", 2);
  await tall
    .waitForFunction(() => document.body.innerText.includes("30 minutes (2 slots)"), {
      timeout: 15000,
    })
    .catch(() => undefined);
  await sleep(1500);
  await clickButton(tall, "12:00");
  await tall.type("textarea", "Physiotherapy");
  await clickButton(tall, "Book the appointment");
  await tall
    .waitForFunction(() => document.body.innerText.includes("Booked:"), { timeout: 20000 })
    .catch(() => undefined);
  const [, longList] = await api("GET", `/patients/${longVisit.id}/appointments`);
  const booked = longList.items[0];
  check(
    "a two-slot visit is booked with its length",
    booked?.slots === 2 && booked?.duration_min === 30,
    JSON.stringify(booked && [booked.slots, booked.duration_min]),
  );

  // 4c a phone number belongs to one patient: registering onto a taken one is refused
  const dup = await openPage(browser, clock);
  await dup.goto(`${BASE_URL}/patients`, { waitUntil: "domcontentloaded" });
  await dup.waitForSelector('[role="search"] input');
  await clickButton(dup, "New patient");
  await dup.waitForSelector('form[aria-label="New patient"]');
  const takenPhone = "9000000001"; // the seeded patient Kavita Nair
  await dup.type('form[aria-label="New patient"] label:nth-of-type(1) input', `Dup ${tag}`);
  await dup.type('form[aria-label="New patient"] label:nth-of-type(2) input', takenPhone);
  await setField(dup, 'form[aria-label="New patient"] label:nth-of-type(3) input', "2012-04-04");
  await clickButton(dup, "Register patient");
  await dup
    .waitForFunction(() => document.body.innerText.includes("already registered"), {
      timeout: 20000,
    })
    .catch(() => undefined);
  const refused = (await dup.evaluate(() => document.body.innerText)).includes(
    "already registered",
  );
  const [, owners] = await api("GET", `/patients?phone=${takenPhone}`);
  check(
    "a taken phone number is refused and still belongs to one patient",
    refused && owners.total === 1,
    `refused=${refused} total=${owners.total}`,
  );

  // 5 search, unknown patient, unknown route
  const search = await openPage(browser, clock);
  await search.goto(`${BASE_URL}/patients`, { waitUntil: "domcontentloaded" });
  await search.waitForSelector('[role="search"] input');
  await search.type('[role="search"] input', "9000000001");
  await clickButton(search, "Search");
  await search
    .waitForFunction(() => document.body.innerText.includes("Kavita"), { timeout: 20000 })
    .catch(() => undefined);
  check(
    "searching by phone finds the seeded patient",
    (await search.evaluate(() => document.body.innerText)).includes("Kavita"),
  );
  await search.goto(`${BASE_URL}/patients/999999`, { waitUntil: "domcontentloaded" });
  await search.waitForSelector(".banner.error", { timeout: 20000 }).catch(() => undefined);
  const unknown = await search.evaluate(
    () => document.querySelector(".banner.error")?.innerText ?? "",
  );
  check(
    "an unknown patient shows a readable error",
    /no patient|not found/i.test(unknown),
    unknown,
  );
  const missing = await search.goto(`${BASE_URL}/no/such/page`, { waitUntil: "domcontentloaded" });
  await search
    .waitForFunction(() => document.body.innerText.includes("Page not found"), { timeout: 20000 })
    .catch(() => undefined);
  check(
    "an unknown route shows the not-found page",
    missing.status() === 200 &&
      (await search.evaluate(() => document.body.innerText)).includes("Page not found"),
  );

  // 6 phone width: no sideways scrolling anywhere, no errors
  const phone = await openPage(browser, clock, 375, 812);
  for (const path of [
    "/day",
    "/book",
    "/queue",
    "/calls",
    "/patients",
    "/patients/1",
    "/admin",
    "/reports",
    "/proof",
  ]) {
    await phone.goto(BASE_URL + path, { waitUntil: "domcontentloaded" });
    await sleep(2500);
    const overflow = await phone.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    check(`phone width ${path}: no horizontal scroll`, overflow <= 0, `${overflow}px`);
  }
  check(
    "no console errors on the phone pages",
    phone.problems.length === 0,
    phone.problems.join(" | "),
  );

  // 6b a day off offers the nearest times; the rule proof runs and keeps nothing
  const leaveDay = addDays(day, 7);
  await api("PUT", `/doctors/${doctor.id}/overrides/${leaveDay}`, {
    windows: [],
    note: "e2e leave",
    acknowledge_conflicts: false,
  });
  const away = await openPage(browser, clock);
  await away.goto(`${BASE_URL}/book?doctor=${doctor.id}&date=${leaveDay}`, {
    waitUntil: "domcontentloaded",
  });
  await away
    .waitForFunction(() => document.body.innerText.includes("Nearest available times"), {
      timeout: 20000,
    })
    .catch(() => undefined);
  const offered = await away.evaluate(
    () => document.querySelectorAll('section[aria-label="Nearest available times"] button').length,
  );
  check("a day off lists the nearest available times", offered > 0, `${offered} offered`);

  const prover = await openPage(browser, clock);
  await prover.goto(`${BASE_URL}/proof`, { waitUntil: "domcontentloaded" });
  await prover.waitForSelector("button.primary");
  await clickButton(prover, "Run the proof");
  await prover
    .waitForFunction(() => document.body.innerText.includes("documented answer"), {
      timeout: 60000,
    })
    .catch(() => undefined);
  const proofText = await prover.evaluate(() => document.body.innerText);
  check(
    "the rule proof passes and keeps nothing",
    /All \d+ scenarios gave the documented answer/.test(proofText) &&
      proofText.includes("nothing kept"),
    proofText.slice(0, 200),
  );
  check(
    "no console errors (including policy violations) on the new pages",
    away.problems.length === 0 && prover.problems.length === 0,
    [...away.problems, ...prover.problems].join(" | "),
  );

  // 7 keyboard: the first Tab lands on a link with a visible outline
  const keys = await openPage(browser, clock);
  await keys.goto(`${BASE_URL}/day`, { waitUntil: "domcontentloaded" });
  await sleep(2000);
  await keys.keyboard.press("Tab");
  const focus = await keys.evaluate(() => {
    const element = document.activeElement;
    const style = getComputedStyle(element);
    return { tag: element.tagName, outline: `${style.outlineStyle} ${style.outlineWidth}` };
  });
  check(
    "the first Tab lands on a link with a visible focus outline",
    focus.tag === "A" && /solid [2-9]px/.test(focus.outline),
    JSON.stringify(focus),
  );
} finally {
  await browser.close();
}
finish();
