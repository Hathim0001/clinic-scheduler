import { useQueryClient } from "@tanstack/react-query";
import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";
import { useAuthStatus, useLogin } from "../api/hooks";
import { getSession, setSession, subscribeSession } from "../lib/authStore";
import { ErrorBanner, Skeleton } from "./common";

export function useSession() {
  return useSyncExternalStore(subscribeSession, getSession);
}

function SignIn() {
  const login = useLogin();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { name, password },
      {
        onSuccess: (result) => {
          setSession({ token: result.token, name: result.name });
          void queryClient.invalidateQueries();
        },
      },
    );
  };

  return (
    <form className="card sign-in" onSubmit={submit} aria-label="Staff sign-in">
      <h1>Sign in</h1>
      <p className="muted">
        Use the clinic&apos;s staff password. Your name is written next to every change you make.
      </p>
      <label>
        Your name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="username"
          maxLength={100}
          required
        />
      </label>
      <label>
        Staff password
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
    </form>
  );
}

/**
 * Shows the app when no sign-in is needed (the server says so) or the person has signed in, and the
 * sign-in form otherwise. The server decides; this only follows.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuthStatus();
  const session = useSession();

  if (status.isPending) return <Skeleton rows={2} />;
  if (status.error)
    return <ErrorBanner error={status.error} onRetry={() => void status.refetch()} />;
  if (status.data.required && !session) return <SignIn />;
  return <>{children}</>;
}
