import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { ApiError } from "./api/client";
import { ClockProvider } from "./lib/clock";
import { getSession, setSession } from "./lib/authStore";
import "@fontsource-variable/inter";
import "@fontsource-variable/playfair-display";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";

// A token that expired, or a password that was changed, shows up as a 401 from whatever the page was
// doing. Dropping the session brings the sign-in form back instead of a page full of error banners.
const signOutOn401 = (error: unknown) => {
  if (error instanceof ApiError && error.code === "UNAUTHENTICATED" && getSession()) {
    setSession(null);
  }
};

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: signOutOn401 }),
  mutationCache: new MutationCache({ onError: signOutOn401 }),
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ClockProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ClockProvider>
    </QueryClientProvider>
  </StrictMode>,
);
