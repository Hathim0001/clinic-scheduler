import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi } from "../test/fakeApi";
import { appointment, doctor, patient, renderPage } from "../test/utils";
import {
  useCancel,
  useCreatePatient,
  useDoctors,
  useJoinWaitlist,
  usePatient,
  usePatientAppointments,
  useQueue,
  useSaveOverride,
} from "./hooks";

/** Draws a few queries and one button per mutation, so a test can see which queries refetch. */
function Probe() {
  useDoctors();
  useQueue("2026-11-02", null, false);
  usePatient(7);
  usePatientAppointments(7);
  const cancel = useCancel();
  const join = useJoinWaitlist();
  const create = useCreatePatient();
  const override = useSaveOverride();
  return (
    <div>
      <button onClick={() => cancel.mutate({ id: 41, by: "PATIENT" })}>cancel</button>
      <button onClick={() => join.mutate({ doctorId: 1, patientId: 7, date: "2026-11-02" })}>
        join
      </button>
      <button
        onClick={() =>
          create.mutate({ name: "A", phone: "9876543210", date_of_birth: "1990-01-01" })
        }
      >
        register
      </button>
      <button
        onClick={() =>
          override.mutate({
            doctorId: 1,
            date: "2026-11-03",
            windows: [],
            note: "",
            acknowledge: false,
          })
        }
      >
        leave
      </button>
    </div>
  );
}

const routes = () => ({
  "GET /doctors": { body: [doctor()] },
  "GET /queue": { body: [appointment()] },
  "GET /patients/7": { body: patient() },
  "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
  "POST /appointments/41/cancel": {
    body: { appointment: appointment({ status: "CANCELLED" }), late: false, deposit: {} },
  },
  "POST /doctors/1/waitlist": { status: 201, body: {} },
  "POST /patients": { status: 201, body: patient({ id: 9 }) },
  "PUT /doctors/1/overrides/2026-11-03": { body: { date: "2026-11-03", windows: [] } },
});

async function settle(count: () => number, expected: number) {
  await waitFor(() => expect(count()).toBe(expected));
}

describe("what a change refreshes", () => {
  it("a cancellation refreshes the queue and the patient's lists but not the doctors", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Probe />);
    await settle(() => api.count("GET", "/queue"), 1);

    await user.click(screen.getByText("cancel"));

    await settle(() => api.count("GET", "/queue"), 2);
    expect(api.count("GET", "/patients/7")).toBe(2); // the deposit flag can change
    expect(api.count("GET", "/patients/7/appointments")).toBe(2);
    expect(api.count("GET", "/doctors")).toBe(1); // untouched
  });

  it("joining the waitlist refreshes nothing else", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Probe />);
    await settle(() => api.count("GET", "/queue"), 1);

    await user.click(screen.getByText("join"));
    await settle(() => api.count("POST", "/doctors/1/waitlist"), 1);
    await new Promise((resolve) => setTimeout(resolve, 150));

    expect(api.count("GET", "/queue")).toBe(1);
    expect(api.count("GET", "/doctors")).toBe(1);
    expect(api.count("GET", "/patients/7")).toBe(1);
  });

  it("registering a patient refreshes patients but not the doctors", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Probe />);
    await settle(() => api.count("GET", "/queue"), 1);

    await user.click(screen.getByText("register"));
    await settle(() => api.count("GET", "/patients/7"), 2);
    await settle(() => api.count("GET", "/queue"), 2); // names show on the queue
    expect(api.count("GET", "/doctors")).toBe(1);
  });

  it("a day off refreshes the doctors and the queue", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Probe />);
    await settle(() => api.count("GET", "/queue"), 1);

    await user.click(screen.getByText("leave"));
    await settle(() => api.count("GET", "/doctors"), 2);
    await settle(() => api.count("GET", "/queue"), 2);
    expect(api.count("GET", "/patients/7")).toBe(1); // a patient's details do not change
  });
});
