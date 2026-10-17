import { Link, NavLink, Navigate, Route, Routes } from "react-router";
import { useNeedsAttention } from "./api/hooks";
import { ClockBar } from "./components/ClockBar";
import { WakeBanner } from "./components/WakeBanner";
import Admin from "./pages/Admin";
import Book from "./pages/Book";
import DayView from "./pages/DayView";
import { PatientDetail, PatientSearch } from "./pages/Patients";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";

function Header() {
  const attention = useNeedsAttention();
  const count = attention.data?.total ?? 0;
  return (
    <header className="app-header">
      <Link to="/day" className="brand">
        Clinic Scheduler
      </Link>
      <nav className="nav" aria-label="Main">
        <NavLink to="/day">Day view</NavLink>
        <NavLink to="/book">Book</NavLink>
        <NavLink to="/queue">Queue</NavLink>
        <NavLink to="/patients">Patients</NavLink>
        <NavLink to="/reports">Report</NavLink>
        <NavLink to="/admin">
          Doctors
          {count > 0 && (
            <span className="badge-attention" aria-label={`${count} appointments need attention`}>
              {count}
            </span>
          )}
        </NavLink>
      </nav>
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
  return (
    <>
      <Header />
      <main>
        <WakeBanner />
        <Routes>
          <Route path="/" element={<Navigate to="/day" replace />} />
          <Route path="/day" element={<DayView />} />
          <Route path="/book" element={<Book />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/patients" element={<PatientSearch />} />
          <Route path="/patients/:id" element={<PatientDetail />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/admin/doctors" element={<Admin />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}
