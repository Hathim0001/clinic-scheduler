import { useQueryClient } from "@tanstack/react-query";
import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";
import { useAuthStatus, useChangePassword, useLogin, useResetPassword } from "../api/hooks";
import { getSession, setSession, subscribeSession } from "../lib/authStore";
import { Banner, ErrorBanner, Skeleton } from "./common";

export function useSession() {
  return useSyncExternalStore(subscribeSession, getSession);
}

/** Can this person set the clinic up? Everyone can while the server asks for no sign-in. */
export function useIsAdmin(): boolean {
  const auth = useAuthStatus();
  const session = useSession();
  if (!auth.data?.required) return true;
  // A session saved before roles existed has none and was the shared password: an administrator.
  return session?.role === undefined || session.role === "ADMIN";
}

/** Is this a doctor's own login (which sees the schedule and marks only their own visits)? */
export function useIsDoctor(): boolean {
  const auth = useAuthStatus();
  const session = useSession();
  return auth.data?.required === true && session?.role === "DOCTOR";
}

/** Choose a new password with the single-use code an administrator gave you. */
function ForgotPassword({ onBack }: { onBack: () => void }) {
  const reset = useResetPassword();
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const mismatch = again !== "" && again !== password;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    reset.mutate({ username, code, new_password: password });
  };

  if (reset.isSuccess) {
    return (
      <div className="card sign-in">
        <h1>Password changed</h1>
        <p>You can now sign in with your new password.</p>
        <div className="actions">
          <button type="button" className="primary" onClick={onBack}>
            Go to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="card sign-in" onSubmit={submit} aria-label="Reset password">
      <h1>Forgot your password?</h1>
      <p className="muted">
        Ask an administrator for a reset code. It works once and for an hour. Then choose a new
        password here.
      </p>
      <label>
        Username
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />
      </label>
      <label>
        Reset code
        <input
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          autoComplete="one-time-code"
          placeholder="K7QX-92MD"
          maxLength={20}
          required
        />
      </label>
      <label>
        New password (at least 8 characters)
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
        New password again
        <input
          type="password"
          value={again}
          onChange={(event) => setAgain(event.target.value)}
          autoComplete="new-password"
          aria-invalid={mismatch}
          required
        />
      </label>
      {mismatch && <p className="rule-wrong">The two passwords are not the same.</p>}
      {reset.error && <ErrorBanner error={reset.error} />}
      <div className="actions">
        <button
          type="submit"
          className="primary"
          disabled={reset.isPending || mismatch || password.length < 8 || !username.trim() || !code}
        >
          {reset.isPending ? "Saving…" : "Set new password"}
        </button>
        <button type="button" onClick={onBack}>
          Back to sign in
        </button>
      </div>
    </form>
  );
}

/** Change your own password: needs the current one, and ends your other sessions. */
export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const mismatch = again !== "" && again !== password;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      { current_password: current, new_password: password },
      // the server ends every older session, this one included: sign in again with the new one
      { onSuccess: () => setSession(null) },
    );
  };

  return (
    <div className="overlay" role="presentation">
      <form
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
        onSubmit={submit}
      >
        <h2 id="change-password-title">Change your password</h2>
        <p className="muted">You will be signed out and can sign in again with the new one.</p>
        <label>
          Current password
          <input
            type="password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          New password (at least 8 characters)
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
          New password again
          <input
            type="password"
            value={again}
            onChange={(event) => setAgain(event.target.value)}
            autoComplete="new-password"
            aria-invalid={mismatch}
            required
          />
        </label>
        {mismatch && <p className="rule-wrong">The two passwords are not the same.</p>}
        {change.error && <ErrorBanner error={change.error} />}
        <div className="actions">
          <button
            type="submit"
            className="primary"
            disabled={change.isPending || mismatch || password.length < 8 || !current}
          >
            {change.isPending ? "Saving…" : "Change password"}
          </button>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function SignIn() {
  const login = useLogin();
  const accounts = useAuthStatus().data?.accounts === true;
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [forgot, setForgot] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { name, password },
      {
        onSuccess: (result) => {
          setSession({
            token: result.token,
            name: result.name,
            role: result.role,
            doctor_id: result.doctor_id ?? null,
          });
          void queryClient.invalidateQueries();
        },
      },
    );
  };

  if (forgot) return <ForgotPassword onBack={() => setForgot(false)} />;

  return (
    <form className="card sign-in" onSubmit={submit} aria-label="Staff sign-in">
      <h1>Sign in</h1>
      <p className="muted">
        {accounts
          ? "Sign in with your own username and password. Your name is written next to every change you make."
          : "Use the clinic's staff password. Your name is written next to every change you make."}
      </p>
      <label>
        {accounts ? "Username" : "Your name"}
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="username"
          maxLength={100}
          required
        />
      </label>
      <label>
        {accounts ? "Password" : "Staff password"}
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      {login.error && <ErrorBanner error={login.error} />}
      <div className="actions">
        <button
          type="submit"
          className="primary"
          disabled={login.isPending || !name.trim() || !password}
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
      </div>
      {accounts && (
        <p>
          <button type="button" className="link" onClick={() => setForgot(true)}>
            Forgot your password?
          </button>
        </p>
      )}
    </form>
  );
}

/**
 * Shows the app when no sign-in is needed (the server says so) or the person has signed in, and the
 * sign-in form otherwise. The server decides; this only follows.
 */
function SetupNeeded() {
  return (
    <div className="card sign-in">
      <h1>Sign-in is not set up yet</h1>
      <p>
        This server requires staff to sign in, so patient details are never open to anyone with the
        link, but nobody has finished setting that up. Whoever runs the server needs to set:
      </p>
      <ul>
        <li>
          <code>AUTH_SECRET</code>: a long random string, 16 characters or more
        </li>
        <li>
          <code>BOOTSTRAP_ADMIN_USERNAME</code> and <code>BOOTSTRAP_ADMIN_PASSWORD</code>: the first
          administrator, created once
        </li>
      </ul>
      <p className="muted">
        For a public demo only, <code>ALLOW_OPEN_ACCESS=true</code> leaves the app open instead, and
        every page then says so.
      </p>
    </div>
  );
}

/** A reminder on every page when sign-in was switched off on purpose. */
export function OpenAccessBanner() {
  const status = useAuthStatus();
  if (!status.data?.open_access) return null;
  return (
    <Banner kind="warn">
      Sign-in is switched off on this server, so anyone with the link can read patient names and
      phone numbers. That is meant for a demo only.
    </Banner>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuthStatus();
  const session = useSession();

  if (status.isPending) return <Skeleton rows={2} />;
  if (status.error)
    return <ErrorBanner error={status.error} onRetry={() => void status.refetch()} />;
  if (status.data.setup_needed) return <SetupNeeded />;
  if (status.data.required && !session) return <SignIn />;
  return <>{children}</>;
}
