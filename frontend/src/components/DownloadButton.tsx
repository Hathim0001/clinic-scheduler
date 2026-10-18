import { useState } from "react";
import { download } from "../api/client";
import { ErrorBanner } from "./common";

interface Props {
  path: string;
  /** Used when the server does not name the file. */
  fallbackName: string;
  label: string;
  query?: Record<string, string | number | boolean | null | undefined>;
}

/**
 * A file download that works when staff sign-in is on. A plain link cannot send the sign-in token,
 * so this fetches the file with it, then hands the browser a temporary link to save it.
 */
export function DownloadButton({ path, fallbackName, label, query }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await download(path, query);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename ?? fallbackName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="link" onClick={() => void save()} disabled={busy}>
        {busy ? "Preparing…" : label}
      </button>
      {error !== null && <ErrorBanner error={error} />}
    </>
  );
}
