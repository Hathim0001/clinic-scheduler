import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router";
import { useAuthStatus, useNeedsAttention, usePendingMessages } from "./api/hooks";
import { setSession } from "./lib/authStore";
import { formatDayIST } from "./lib/formatIST";
import { useToday } from "./lib/useToday";
import { AuthGate, useIsAdmin, useSession } from "./components/AuthGate";
import { ClockBar } from "./components/ClockBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OfflineBanner, SkipLink, useRouteAccessibility } from "./components/PageChrome";
import { Avatar, Icon, type IconName } from "./components/ui";
import { UndoCancel } from "./components/UndoCancel";
import { WakeBanner } from "./components/WakeBanner";
import Admin from "./pages/Admin";
import Book from "./pages/Book";
import DayView from "./pages/DayView";
import { PatientDetail, PatientSearch } from "./pages/Patients";
import Calls from "./pages/Calls";
import Messages from "./pages/Messages";
import Overview from "./pages/Overview";
import Proof from "./pages/Proof";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";
import Staff from "./pages/Staff";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  badge?: number;
  badgeLabel?: string;
  end?: boolean;
}

function NavSection({ heading, items }: { heading: string; items: NavItem[] }) {
  return (
    <div className="nav-section">
      <p className="nav-heading">{heading}</p>
      <ul>
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} end={item.end}>
              <Icon name={item.icon} size={18} />
              <span className="nav-label">{item.label}</span>
              {item.badge ? (
                <span className="badge-attention" aria-label={item.badgeLabel}>
                  {item.badge}
                </span>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const attention = useNeedsAttention().data?.total ?? 0;
  const messagesWaiting = usePendingMessages().data?.count ?? 0;
  const session = useSession();
  const auth = useAuthStatus();
  const isAdmin = useIsAdmin();

  const schedule: NavItem[] = [
    { to: "/", label: "Overview", icon: "overview", end: true },
    { to: "/day", label: "Day view", icon: "calendar" },
    { to: "/book", label: "Book", icon: "plus" },
    { to: "/queue", label: "Queue", icon: "queue" },
  ];
  const people: NavItem[] = [
    { to: "/patients", label: "Patients", icon: "people" },
    { to: "/calls", label: "Calls", icon: "phone" },
    {
      to: "/messages",
      label: "Messages",
      icon: "message",
      badge: messagesWaiting,
      badgeLabel: `${messagesWaiting} messages waiting`,
    },
  ];
  const clinic: NavItem[] = [
    { to: "/reports", label: "Report", icon: "chart" },
    {
      to: "/admin",
      label: "Doctors",
      icon: "doctor",
      badge: attention,
      badgeLabel: `${attention} appointments need attention`,
    },
  ];
  if (isAdmin && auth.data?.accounts) clinic.push({ to: "/staff", label: "Staff", icon: "key" });
  if (isAdmin) clinic.push({ to: "/proof", label: "Prove the rules", icon: "shield" });

  return (
    <aside className={open ? "sidebar open" : "sidebar"} id="sidebar">
      <div className="sidebar-top">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="plus" size={16} />
          </span>
          Clinic Scheduler
        </Link>
        <button type="button" className="icon-button sidebar-close" onClick={onClose}>
          <Icon name="close" size={18} />
          <span className="visually-hidden">Close menu</span>
        </button>
      </div>
      <nav className="nav" aria-label="Main">
        <NavSection heading="Schedule" items={schedule} />
        <NavSection heading="Patients" items={people} />
        <NavSection heading="Clinic" items={clinic} />
      </nav>
      {auth.data?.required && session && (
        <div className="sidebar-user">
          <Avatar name={session.name} />
          <div className="sidebar-user-text">
            <strong>{session.name}</strong>
            <span>{session.role === "ADMIN" ? "Administrator" : "Reception"}</span>
          </div>
          <button type="button" className="small" onClick={() => setSession(null)}>
            Sign out ({session.name})
          </button>
        </div>
      )}
    </aside>
  );
}

function Topbar({ onMenu, menuOpen }: { onMenu: () => void; menuOpen: boolean }) {
  const today = useToday();
  return (
    <div className="topbar">
      <button
        type="button"
        className="icon-button menu-button"
        aria-expanded={menuOpen}
        aria-controls="sidebar"
        onClick={onMenu}
      >
        <Icon name="menu" size={20} />
        <span className="visually-hidden">Menu</span>
      </button>
      <span className="topbar-date">
        {today ? formatDayIST(`${today}T12:00:00+05:30`) : "Clinic Scheduler"}
      </span>
      <Link to="/book" className="primary topbar-action">
        <Icon name="plus" size={16} />
        New booking
      </Link>
    </div>
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

function Shell() {
  const main = useRouteAccessibility();
  const { pathname } = useLocation();
  // The menu belongs to the page it was opened on: moving to another page closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenOn(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className={open ? "app-shell menu-open" : "app-shell"}>
      <Sidebar open={open} onClose={() => setOpenOn(null)} />
      <div className="app-scrim" onClick={() => setOpenOn(null)} aria-hidden="true" />
      <div className="app-body">
        <header className="app-header">
          <Topbar onMenu={() => setOpenOn(open ? null : pathname)} menuOpen={open} />
        </header>
        <ClockBar />
        <main id="main" ref={main} tabIndex={-1}>
          <OfflineBanner />
          <WakeBanner />
          <UndoCancel />
          <Routes>
            <Route path="/" element={<Overview />} />
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
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <SkipLink />
      <AuthGate>
        <Shell />
      </AuthGate>
    </ErrorBoundary>
  );
}
