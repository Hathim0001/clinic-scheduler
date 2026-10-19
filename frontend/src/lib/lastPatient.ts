const KEY = "clinic.lastPatientId";

/** The patient of the last successful booking in this browser tab, so booking again starts there. */
export function readLastPatient(): number | null {
  try {
    return Number(window.sessionStorage.getItem(KEY)) || null;
  } catch {
    return null; // storage can be blocked; booking works without it
  }
}

export function rememberPatient(id: number): void {
  try {
    window.sessionStorage.setItem(KEY, String(id));
  } catch {
    // nothing to do: the next booking simply starts with nobody selected
  }
}
