import { Link, NavLink, Navigate, Route, Routes } from "react-router";
import { useAuthStatus, useNeedsAttention } from "./api/hooks";
import { setSession } from "./lib/authStore";
import { AuthGate, useSession } from "./components/AuthGate";
import { ClockBar } from "./components/ClockBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OfflineBanner, SkipLink, useRouteAccessibility } from "./components/PageChrome";
import { WakeBanner } from "./components/WakeBanner";
import Admin from "./pages/Admin";
import Book from "./pages/Book";
import DayView from "./pages/DayView";
import { PatientDetail, PatientSearch } from "./pages/Patients";
import Proof from "./pages/Proof";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";

function Header() {
  const attention = useNeedsAttention();
  const count = attention.data?.total ?? 0;
  const session = useSession();
  const auth = useAuthStatus();
  return (
    <header className="app-header">
      <div className="app-header-bar">
        <Link to="/day" className="brand">
          Clinic Scheduler
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/day">Day view</NavLink>
          <NavLink to="/book">Book</NavLink>
          <NavLink to="/queue">Queue</NavLink>
          <NavLink to="/patients">Patients</NavLink>
          <NavLink to="/reports">Report</NavLink>
          <NavLink to="/proof">Proof</NavLink>
          <NavLink to="/admin">
            Doctors
            {count > 0 && (
              <span className="badge-attention" aria-label={`${count} appointments need attention`}>
                {count}
              </span>
            )}
          </NavLink>
        </nav>
        {auth.data?.required && session && (
          <button type="button" className="small signed-in" onClick={() => setSession(null)}>
            Sign out ({session.name})
          </button>
        )}
      </div>
      <ClockBar />
    </header>
  );
}

function NotFound() {
  return (
    <div>
      <h1>Page not found</h1>
      <p>
        <Link to="/day">Go to the day view</Link>
      </p>
    </div>
  );
}

export default function App() {
  const main = useRouteAccessibility();
  return (
    <ErrorBoundary>
      <SkipLink />
      <AuthGate>
        <Header />
        <main id="main" ref={main} tabIndex={-1}>
          <OfflineBanner />
          <WakeBanner />
          <Routes>
            <Route path="/" element={<Navigate to="/day" replace />} />
            <Route path="/day" element={<DayView />} />
            <Route path="/book" element={<Book />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/patients" element={<PatientSearch />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/proof" element={<Proof />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/admin/doctors" element={<Admin />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </AuthGate>
    </ErrorBoundary>
  );
}
