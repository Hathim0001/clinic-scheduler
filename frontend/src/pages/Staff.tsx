import { useState, type FormEvent } from "react";
import {
  useAuthStatus,
  useCreateStaff,
  useDoctors,
  useIssueResetCode,
  useStaff,
  useUpdateStaff,
} from "../api/hooks";
import type { Role, StaffAccount } from "../api/types";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { PageHeader } from "../components/ui";
import { formatTimeIST } from "../lib/formatIST";
import { useIsAdmin } from "../components/AuthGate";

const ROLE_TEXT: Record<Role, string> = {
  ADMIN: "Administrator",
  RECEPTIONIST: "Receptionist",
  DOCTOR: "Doctor",
};

/** The roles a row can be switched between: a doctor's login is tied to a doctor, so it stays. */
const SWITCHABLE: Role[] = ["ADMIN", "RECEPTIONIST"];

/** Staff accounts: who can sign in and as what. Administrators only (the server enforces it). */
export default function Staff() {
  const isAdmin = useIsAdmin();
  const statusKnown = useAuthStatus().isSuccess; // do not ask before we know who is asking
  const staff = useStaff(isAdmin && statusKnown);

  if (!isAdmin) {
    return (
      <div>
        <h1>Staff</h1>
        <Banner kind="info">Only an administrator can manage staff accounts.</Banner>
      </div>
    );
  }
  return (
    <div>
      <PageHeader
        title="Staff accounts"
        description="An administrator also sets up doctors, hours and the clinic's rules and can erase a patient's data. A receptionist runs the day: patients, bookings, the queue and the waitlist. A doctor sees the schedule and marks their own visits."
      />
      {staff.isPending && <Skeleton rows={3} />}
      {staff.error && <ErrorBanner error={staff.error} onRetry={() => void staff.refetch()} />}
      {staff.data && staff.data.length === 0 && (
        <p className="muted">
          No individual accounts yet. Create the first administrator below, then sign in with it.
        </p>
      )}
      {staff.data && staff.data.length > 0 && (
        <div className="table-scroll" role="region" aria-label="Staff accounts" tabIndex={0}>
          <table className="stack">
            <caption className="visually-hidden">Staff accounts</caption>
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Name</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {staff.data.map((account) => (
                <StaffRow key={account.id} account={account} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NewStaff />
    </div>
  );
}

function StaffRow({ account }: { account: StaffAccount }) {
  const update = useUpdateStaff();
  const issue = useIssueResetCode();
  const doctors = useDoctors();
  const [password, setPassword] = useState("");
  const [resetting, setResetting] = useState(false);
  const doctorName = doctors.data?.find((d) => d.id === account.doctor_id)?.name;

  return (
    <tr>
      <th scope="row" data-label="Username">
        {account.username}
      </th>
      <td data-label="Name">{account.display_name}</td>
      <td data-label="Role">
        {account.role === "DOCTOR" ? (
          <span>
            Doctor
            {doctorName && <span className="muted"> ({doctorName})</span>}
          </span>
        ) : (
          <select
            aria-label={`Role of ${account.username}`}
            value={account.role}
            onChange={(event) =>
              update.mutate({ id: account.id, changes: { role: event.target.value as Role } })
            }
          >
            {SWITCHABLE.map((role) => (
              <option key={role} value={role}>
                {ROLE_TEXT[role]}
              </option>
            ))}
          </select>
        )}
      </td>
      <td data-label="Status">{account.active ? "Active" : "Switched off"}</td>
      <td data-label="Actions">
        <button
          type="button"
          onClick={() => update.mutate({ id: account.id, changes: { active: !account.active } })}
        >
          {account.active ? "Switch off" : "Switch on"} {account.username}
        </button>{" "}
        {resetting ? (
          <span>
            <input
              type="password"
              aria-label={`New password for ${account.username}`}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={8}
            />{" "}
            <button
              type="button"
              disabled={password.length < 8}
              onClick={() =>
                update.mutate(
                  { id: account.id, changes: { password } },
                  {
                    onSuccess: () => {
                      setPassword("");
                      setResetting(false);
                    },
                  },
                )
              }
            >
              Save password
            </button>
          </span>
        ) : (
          <>
            <button type="button" onClick={() => setResetting(true)}>
              Reset password for {account.username}
            </button>{" "}
            <button
              type="button"
              onClick={() => issue.mutate(account.id)}
              disabled={issue.isPending}
            >
              Issue a reset code for {account.username}
            </button>
          </>
        )}
        {issue.data && (
          <Banner kind="success">
            <p>
              Reset code for {account.display_name}:{" "}
              <code className="reset-code">{issue.data.code}</code>
            </p>
            <p>
              It works once and stops working at {formatTimeIST(issue.data.expires_at_utc)} India
              time. Give it to them in person or by phone; they choose a new password on the sign-in
              page (&ldquo;Forgot your password?&rdquo;). It is not shown again.
            </p>
          </Banner>
        )}
        {issue.error && <ErrorBanner error={issue.error} />}
        {update.error && <ErrorBanner error={update.error} />}
      </td>
    </tr>
  );
}

function NewStaff() {
  const create = useCreateStaff();
  const doctors = useDoctors();
  const [doctorId, setDoctorId] = useState<number | null>(null);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("RECEPTIONIST");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      {
        username,
        display_name: displayName,
        password,
        role,
        doctor_id: role === "DOCTOR" ? (doctorId ?? undefined) : undefined,
      },
      {
        onSuccess: () => {
          setUsername("");
          setDisplayName("");
          setPassword("");
        },
      },
    );
  };

  return (
    <form className="card" onSubmit={submit} aria-label="New staff account">
      <h2>New account</h2>
      <div className="row">
        <label>
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value.toLowerCase())}
            pattern="[a-z0-9._-]{3,40}"
            title="3 to 40 lower-case letters, digits, dots, dashes or underscores"
            required
          />
        </label>
        <label>
          Name shown in the history
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            maxLength={100}
            required
          />
        </label>
        <label>
          Password (at least 8 characters)
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            {(Object.keys(ROLE_TEXT) as Role[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_TEXT[r]}
              </option>
            ))}
          </select>
        </label>
        {role === "DOCTOR" && (
          <label>
            Which doctor
            <select
              value={doctorId ?? ""}
              onChange={(event) => setDoctorId(Number(event.target.value) || null)}
              required
            >
              <option value="">Choose a doctor</option>
              {doctors.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="submit" className="primary" disabled={create.isPending}>
          Create account
        </button>
      </div>
      {create.error && <ErrorBanner error={create.error} />}
      {create.isSuccess && <Banner kind="success">Account created.</Banner>}
    </form>
  );
}
