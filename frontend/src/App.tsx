import { Link, NavLink, Navigate, Route, Routes } from "react-router";
import { useAuthStatus, useNeedsAttention, usePendingMessages } from "./api/hooks";
import { setSession } from "./lib/authStore";
import { AuthGate, useIsAdmin, useSession } from "./components/AuthGate";
import { ClockBar } from "./components/ClockBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { NavMenu } from "./components/NavMenu";
import { OfflineBanner, SkipLink, useRouteAccessibility } from "./components/PageChrome";
import { UndoCancel } from "./components/UndoCancel";
import { WakeBanner } from "./components/WakeBanner";
import Admin from "./pages/Admin";
import Book from "./pages/Book";
import DayView from "./pages/DayView";
import { PatientDetail, PatientSearch } from "./pages/Patients";
import Calls from "./pages/Calls";
import Messages from "./pages/Messages";
import Proof from "./pages/Proof";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";
import Staff from "./pages/Staff";

function Header() {
  const attention = useNeedsAttention();
  const count = attention.data?.total ?? 0;
  const messagesWaiting = usePendingMessages().data?.count ?? 0;
  const session = useSession();
  const auth = useAuthStatus();
  const isAdmin = useIsAdmin();
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
          <NavLink to="/calls">Calls</NavLink>
          <NavLink to="/patients">Patients</NavLink>
          <NavMenu
            label="More"
            paths={["/messages", "/reports", "/admin", "/proof", "/staff"]}
            badge={count + messagesWaiting}
            badgeLabel={`${count + messagesWaiting} items need attention`}
          >
            <li>
              <NavLink to="/messages">
                Messages
                {messagesWaiting > 0 && (
                  <span
                    className="badge-attention"
                    aria-label={`${messagesWaiting} messages waiting`}
                  >
                    {messagesWaiting}
                  </span>
                )}
              </NavLink>
            </li>
            <li>
              <NavLink to="/reports">Report</NavLink>
            </li>
            <li>
              <NavLink to="/admin">
                Doctors
                {count > 0 && (
                  <span
                    className="badge-attention"
                    aria-label={`${count} appointments need attention`}
                  >
                    {count}
                  </span>
                )}
              </NavLink>
            </li>
            {isAdmin && auth.data?.accounts && (
              <li>
                <NavLink to="/staff">Staff</NavLink>
              </li>
            )}
            {isAdmin && (
              <li>
                <NavLink to="/proof">Prove the rules</NavLink>
              </li>
            )}
          </NavMenu>
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
          <UndoCancel />
          <Routes>
            <Route path="/" element={<Navigate to="/day" replace />} />
            <Route path="/day" element={<DayView />} />
            <Route path="/book" element={<Book />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/calls" element={<Calls />} />
            <Route path="/patients" element={<PatientSearch />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/proof" element={<Proof />} />
            <Route path="/staff" element={<Staff />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/admin/doctors" element={<Admin />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </AuthGate>
    </ErrorBoundary>
  );
}
