import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import { homeFor } from "./lib/nav";
import type { Role } from "./lib/types";
import DemoScenarios from "./pages/DemoScenarios";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";

const Dashboard = lazy(() => import("./pages/patient/Dashboard"));
const JourneyPage = lazy(() => import("./pages/patient/JourneyPage"));
const DocumentsPage = lazy(() => import("./pages/patient/DocumentsPage"));
const DocumentDetail = lazy(() => import("./pages/DocumentDetail"));
const CareGapsPage = lazy(() => import("./pages/patient/CareGapsPage"));
const Tasks = lazy(() => import("./pages/patient/Tasks"));
const Sharing = lazy(() => import("./pages/patient/Sharing"));
const Privacy = lazy(() => import("./pages/patient/Privacy"));
const Consultations = lazy(() => import("./pages/Consultations"));
const ConsultationDetail = lazy(() => import("./pages/ConsultationDetail"));
const MeetingRoom = lazy(() => import("./pages/MeetingRoom"));
const Assistant = lazy(() => import("./pages/Assistant"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Help = lazy(() => import("./pages/Help"));
const Settings = lazy(() => import("./pages/Settings"));
const Workspace = lazy(() => import("./pages/pro/Workspace"));
const PatientView = lazy(() => import("./pages/pro/PatientView"));
const Admin = lazy(() => import("./pages/admin/Admin"));

function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
  if (roles && !roles.includes(user.role)) return <NotFound />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? <Navigate to={homeFor(user.role)} replace /> : <Landing />;
}

const P: Role[] = ["patient"];
const C: Role[] = ["patient", "professional"];

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/demo" element={<DemoScenarios />} />
        <Route path="/app/consultations/:id/room" element={<RequireAuth roles={C}><MeetingRoom /></RequireAuth>} />
        <Route path="/app" element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Home />} />
          <Route path="dashboard" element={<RequireAuth roles={P}><Dashboard /></RequireAuth>} />
          <Route path="journey" element={<RequireAuth roles={P}><JourneyPage /></RequireAuth>} />
          <Route path="documents" element={<RequireAuth roles={P}><DocumentsPage /></RequireAuth>} />
          <Route path="documents/:id" element={<RequireAuth roles={C}><DocumentDetail /></RequireAuth>} />
          <Route path="care-gaps" element={<RequireAuth roles={P}><CareGapsPage /></RequireAuth>} />
          <Route path="tasks" element={<RequireAuth roles={P}><Tasks /></RequireAuth>} />
          <Route path="sharing" element={<RequireAuth roles={P}><Sharing /></RequireAuth>} />
          <Route path="privacy" element={<RequireAuth roles={P}><Privacy /></RequireAuth>} />
          <Route path="consultations" element={<RequireAuth roles={C}><Consultations /></RequireAuth>} />
          <Route path="consultations/:id" element={<RequireAuth roles={C}><ConsultationDetail /></RequireAuth>} />
          <Route path="assistant" element={<RequireAuth roles={C}><Assistant /></RequireAuth>} />
          <Route path="pro" element={<RequireAuth roles={["professional"]}><Workspace /></RequireAuth>} />
          <Route path="pro/patients/:pid" element={<RequireAuth roles={["professional"]}><PatientView /></RequireAuth>} />
          <Route path="admin" element={<RequireAuth roles={["admin"]}><Admin /></RequireAuth>} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="help" element={<Help />} />
          <Route path="help/:slug" element={<Help />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
