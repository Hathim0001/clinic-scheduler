import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router";
import { useAuthStatus, useNeedsAttention, usePendingMessages } from "./api/hooks";
import { SERVER_ROOT } from "./api/client";
import { setSession } from "./lib/authStore";
import { formatDayIST } from "./lib/formatIST";
import { useFocusTrap } from "./lib/useFocusTrap";
import { useSpotlight } from "./lib/useSpotlight";
import { useToday } from "./lib/useToday";
import {
  AuthGate,
  ChangePasswordDialog,
  OpenAccessBanner,
  useIsAdmin,
  useIsDoctor,
  useSession,
} from "./components/AuthGate";
import { ClockBar } from "./components/ClockBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OfflineBanner, SkipLink, useRouteAccessibility } from "./components/PageChrome";
import { Avatar, BrandMark, Icon, type IconName } from "./components/ui";
import { UndoCancel } from "./components/UndoCancel";
import { WakeBanner } from "./components/WakeBanner";
import Admin from "./pages/Admin";
import Book from "./pages/Book";
import DayView from "./pages/DayView";
import { PatientDetail, PatientSearch } from "./pages/Patients";
import Calls from "./pages/Calls";
import Messages from "./pages/Messages";
import MyDay from "./pages/MyDay";
import Overview from "./pages/Overview";
import Policies from "./pages/Policies";
import Proof from "./pages/Proof";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";
import Staff from "./pages/Staff";

/** The group in the menu a page belongs to, shown as the small label above its title. */
const SECTIONS: [prefix: string, section: string][] = [
  ["/my-day", "Schedule"],
  ["/day", "Schedule"],
  ["/book", "Schedule"],
  ["/queue", "Schedule"],
  ["/patients", "Patients"],
  ["/calls", "Patients"],
  ["/messages", "Patients"],
  ["/reports", "Clinic"],
  ["/admin", "Clinic"],
  ["/policies", "Clinic"],
  ["/staff", "Clinic"],
  ["/proof", "Clinic"],
];

const sectionOf = (path: string): string | undefined =>
  path === "/"
    ? "Schedule"
    : SECTIONS.find(([prefix]) => path === prefix || path.startsWith(`${prefix}/`))?.[1];

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  badge?: number;
  badgeLabel?: string;
  end?: boolean;
  /** A page outside the app, opened in a new tab (the API reference). */
  href?: string;
}

function NavSection({ heading, items }: { heading: string; items: NavItem[] }) {
  return (
    <div className="nav-section">
      <p className="nav-heading">{heading}</p>
      <ul>
        {items.map((item) => (
          <li key={item.to}>
            {item.href ? (
              <a href={item.href} target="_blank" rel="noreferrer">
                <Icon name={item.icon} size={18} />
                <span className="nav-label">{item.label}</span>
                <span className="visually-hidden">(opens in a new tab)</span>
              </a>
            ) : (
              <NavLink to={item.to} end={item.end} viewTransition>
                <Icon name={item.icon} size={18} />
                <span className="nav-label">{item.label}</span>
                {item.badge ? (
                  <span className="badge-attention" aria-label={item.badgeLabel}>
                    {item.badge}
                  </span>
                ) : null}
              </NavLink>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Sidebar({
  open,
  onClose,
  containerRef,
}: {
  open: boolean;
  onClose: () => void;
  containerRef: React.RefObject<HTMLDivElement | null>;
}) {
  const attention = useNeedsAttention().data?.total ?? 0;
  const messagesWaiting = usePendingMessages().data?.count ?? 0;
  const auth = useAuthStatus();
  const isAdmin = useIsAdmin();
  const isDoctor = useIsDoctor();

  // A doctor's own login reads the schedule and marks their own visits; the server refuses the
  // rest, so the menu does not offer it.
  const schedule: NavItem[] = [
    { to: "/", label: "Overview", icon: "overview", end: true },
    { to: "/my-day", label: "My day", icon: "pulse" },
    { to: "/day", label: "Day view", icon: "calendar" },
    ...(isDoctor ? [] : [{ to: "/book", label: "Book", icon: "plus" as IconName }]),
    { to: "/queue", label: "Queue", icon: "queue" },
  ];
  const people: NavItem[] = [{ to: "/patients", label: "Patients", icon: "people" }];
  if (!isDoctor) {
    people.push(
      { to: "/calls", label: "Calls", icon: "phone" },
      {
        to: "/messages",
        label: "Messages",
        icon: "message",
        badge: messagesWaiting,
        badgeLabel: `${messagesWaiting} messages waiting`,
      },
    );
  }
  const clinic: NavItem[] = [{ to: "/reports", label: "Report", icon: "chart" }];
  if (!isDoctor) {
    clinic.push(
      {
        to: "/admin",
        label: "Doctors",
        icon: "doctor",
        badge: attention,
        badgeLabel: `${attention} appointments need attention`,
      },
      { to: "/policies", label: "Clinic rules", icon: "sliders" },
    );
  }
  if (isAdmin && auth.data?.accounts) clinic.push({ to: "/staff", label: "Staff", icon: "key" });
  if (isAdmin) clinic.push({ to: "/proof", label: "Prove the rules", icon: "shield" });
  // The interactive reference (Swagger UI) lists every endpoint the app uses.
  if (isAdmin)
    clinic.push({
      to: "/api-docs",
      label: "API reference",
      icon: "code",
      href: `${SERVER_ROOT}/docs`,
    });

  return (
    <div className={open ? "sidebar open" : "sidebar"} id="sidebar" ref={containerRef}>
      <div className="sidebar-top">
        <p className="brand-tagline">Menu</p>
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
    </div>
  );
}

/** Who is signed in, with the two things a person does about it. */
function UserMenu() {
  const session = useSession();
  const auth = useAuthStatus();
  const [changingPassword, setChangingPassword] = useState(false);
  const details = useRef<HTMLDetailsElement>(null);

  // the small panel closes on a click anywhere else and on Escape
  useEffect(() => {
    const close = () => details.current?.removeAttribute("open");
    const onClick = (event: MouseEvent) => {
      if (!details.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && details.current?.hasAttribute("open")) {
        close();
        details.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!auth.data?.required || !session) return null;
  const role =
    session.role === "ADMIN" ? "Administrator" : session.role === "DOCTOR" ? "Doctor" : "Reception";
  return (
    <>
      <details className="user-menu" ref={details}>
        <summary>
          <Avatar name={session.name} />
          <span className="user-menu-name">{session.name}</span>
        </summary>
        <div className="user-pop">
          <p>
            <strong>{session.name}</strong>
            <span>{role}</span>
          </p>
          {auth.data.accounts && (
            <button
              type="button"
              className="small"
              onClick={() => {
                details.current?.removeAttribute("open");
                setChangingPassword(true);
              }}
            >
              Change password
            </button>
          )}
          <button type="button" className="small" onClick={() => setSession(null)}>
            Sign out ({session.name})
          </button>
        </div>
      </details>
      {changingPassword && <ChangePasswordDialog onClose={() => setChangingPassword(false)} />}
    </>
  );
}

function Topbar({ onMenu, menuOpen }: { onMenu: () => void; menuOpen: boolean }) {
  const today = useToday();
  const isDoctor = useIsDoctor();
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
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          <BrandMark />
        </span>
        <span className="brand-name">Clinic Scheduler</span>
      </Link>
      <span className="topbar-date">{today ? formatDayIST(`${today}T12:00:00+05:30`) : ""}</span>
      {!isDoctor && (
        <Link to="/book" className="primary topbar-action">
          <Icon name="plus" size={16} />
          <span>New booking</span>
        </Link>
      )}
      <UserMenu />
    </div>
  );
}

function NotFound() {
  return (
    <div>
      <h1>Page not found</h1>
      <p className="muted">That address does not match a page in the app.</p>
      <p>
        <Link className="primary" to="/">
          Go to the overview
        </Link>
      </p>
    </div>
  );
}

function Shell() {
  const main = useRouteAccessibility();
  const isDoctor = useIsDoctor();
  const { pathname } = useLocation();
  // The menu belongs to the page it was opened on: moving to another page closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const sidebarRef = useRef<HTMLDivElement>(null);
  useFocusTrap(sidebarRef, open, () => setOpenOn(null));
  useSpotlight();

  return (
    <div className={open ? "app-shell menu-open" : "app-shell"}>
      <div className="app-scrim" onClick={() => setOpenOn(null)} aria-hidden="true" />
      <header className="masthead">
        <Topbar onMenu={() => setOpenOn(open ? null : pathname)} menuOpen={open} />
        <Sidebar open={open} onClose={() => setOpenOn(null)} containerRef={sidebarRef} />
      </header>
      <div className="app-body">
        <OpenAccessBanner />
        <ClockBar />
        <main id="main" ref={main} tabIndex={-1} data-section={sectionOf(pathname)}>
          <OfflineBanner />
          <WakeBanner />
          <UndoCancel />
          <Routes>
            <Route path="/" element={isDoctor ? <Navigate to="/my-day" replace /> : <Overview />} />
            <Route path="/my-day" element={<MyDay />} />
            <Route path="/policies" element={<Policies />} />
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
