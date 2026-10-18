import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

/**
 * Catches an unexpected error while drawing a page, so one broken component shows a message and a way
 * back instead of a blank screen. Errors from the API are not caught here: they are ordinary results
 * that each page already shows as a banner.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("The page failed to draw", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="card" role="alert">
        <h1>This page could not be shown</h1>
        <p>
          Something went wrong while drawing it. Nothing you booked or changed is lost. Reload the
          page to try again.
        </p>
        <div className="actions">
          <button type="button" className="primary" onClick={() => window.location.reload()}>
            Reload the page
          </button>
          <a href="/day">Go to the day view</a>
        </div>
      </div>
    );
  }
}
