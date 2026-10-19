// Takes the README's screenshots from the running stack: one for each business rule, plus the main
// pages. Run against a freshly seeded local stack (open access), for example:
//
//   docker compose exec -T backend python -m scripts.migrate_and_seed --reset
//   node e2e/screenshots.mjs
//
// The pictures go to docs/screenshots/. The clock is set to the seed morning, so the dates in the
// pictures match the seed scenarios listed in the README.

import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { API_URL, BASE_URL, addDays, launch, openPage, sleep } from "./lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "..", "docs", "screenshots");
await mkdir(join(out, "rules"), { recursive: true });

const info = await (await fetch(`${API_URL}/clock`)).json();
const monday = info.seed_queue_day; // the seed's busy day
const clock = `${monday}T09:30:00+05:30`;
const [tuesday, wednesday, friday] = [1, 2, 4].map((n) => addDays(monday, n));
const headers = { "content-type": "application/json", "X-Test-Clock": clock };

const get = async (path) => (await fetch(`${API_URL}${path}`, { headers })).json();
const post = async (path, body) =>
  fetch(`${API_URL}${path}`, { method: "POST", headers, body: JSON.stringify(body) });

const doctors = await get("/doctors");
const rao = doctors.find((d) => d.name.includes("Rao"));
const menon = doctors.find((d) => d.name.includes("Menon"));
const patient = async (name) => (await get(`/patients?q=${encodeURIComponent(name)}`)).items[0];
const arjun = await patient("Arjun");
const kavita = await patient("Kavita");
const queue = await get(`/queue?date=${monday}`);

const browser = await launch();
const shot = async (file, path, { width = 1280, height = 900, full = true, before } = {}) => {
  const page = await openPage(browser, clock, width, height);
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  await page.goto(BASE_URL + path, { waitUntil: "domcontentloaded" });
  await sleep(3200);
  if (before) await before(page);
  await page.screenshot({ path: join(out, file), fullPage: full });
  await page.close();
  console.log("saved", file);
};

try {
  // the pages
  await shot("overview.png", "/");
  await shot("day-view.png", `/day?doctor=${rao.id}&date=${tuesday}`);
  await shot("queue.png", `/queue?date=${monday}`);
  await shot("phone-375px.png", `/queue?date=${monday}`, { width: 375, height: 800 });

  // rule 1: only times on the doctor's grid and inside the doctor's hours are offered
  await shot(
    "rules/1-availability-and-grid.png",
    `/book?patient=${arjun.id}&doctor=${rao.id}&date=${wednesday}`,
  );
  // rule 2: a doctor is never booked twice at once: taken slots are filled and cannot be picked
  await shot("rules/2-doctor-never-double-booked.png", `/day?doctor=${rao.id}&date=${tuesday}`);
  // rule 3: a patient is never booked twice at once: Arjun is with Dr. Rao at 10:00 on the 19th,
  // so that time is missing from Dr. Menon's list for him
  await shot(
    "rules/3-patient-never-double-booked.png",
    `/book?patient=${arjun.id}&doctor=${menon.id}&date=${monday}`,
  );
  // rule 4: the daily cap. Dr. Menon, Friday: five of six booked, then the sixth is taken and the rest close
  await shot("rules/4-daily-cap-before.png", `/day?doctor=${menon.id}&date=${friday}`);
  const freeSlots = (await get(`/doctors/${menon.id}/slots?date=${friday}`)).slots ?? [];
  if (freeSlots.length > 0) {
    const sixth = await patient("Sneha");
    await post("/appointments", {
      doctor_id: menon.id,
      patient_id: sixth.id,
      start_at: freeSlots[0].start_at_ist,
      reason: "Cap demonstration",
    });
  }
  await shot("rules/4-daily-cap-reached.png", `/day?doctor=${menon.id}&date=${friday}`);
  // rule 5: a flagged patient must acknowledge a deposit; a cancellation inside 2 hours is late
  await shot(
    "rules/5-deposit-after-two-strikes.png",
    `/book?patient=${kavita.id}&doctor=${rao.id}&date=${tuesday}`,
  );
  const lateOne = queue.find((a) => a.start_at_ist.includes("T11:15") && a.status === "BOOKED");
  await shot("rules/5-late-cancellation.png", `/queue?date=${monday}`, {
    full: false,
    height: 1200,
    before: async (page) => {
      await page.evaluate((id) => {
        const rows = [...document.querySelectorAll("tbody tr")];
        const row = rows.find((r) => r.querySelector(`a[href="/patients/${id}"]`));
        [...(row ?? document).querySelectorAll("button")]
          .find((b) => /Cancel/.test(b.innerText))
          ?.click();
      }, lateOne?.patient_id);
      await sleep(900);
    },
  });
  // rule 6: a reschedule cancels the old slot and books the new one together
  const moving = queue.find((a) => a.status === "BOOKED");
  await shot("rules/6-reschedule-is-atomic.png", `/book?reschedule=${moving.id}`);
  // rule 7: nothing in the past, nothing more than 60 days ahead
  await shot(
    "rules/7-booking-window.png",
    `/book?patient=${arjun.id}&doctor=${rao.id}&date=${addDays(monday, 73)}`,
  );
  await shot("rules/proof-of-all-rules.png", "/proof", {
    before: async (page) => {
      await page.evaluate(() =>
        [...document.querySelectorAll("button")].find((b) => /Run/.test(b.innerText))?.click(),
      );
      await sleep(6000);
    },
  });
} finally {
  await browser.close();
}
