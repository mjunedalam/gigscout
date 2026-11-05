import { Center, Loader } from "@mantine/core";
import { lazy, type ReactNode, Suspense } from "react";
import { createBrowserRouter } from "react-router";

import { AppLayout } from "./AppLayout";
import { RequireAdmin, RequirePlatformAdmin, RequireAuth } from "./guards";

// Route-level code splitting: each screen (and its charts) loads on first visit.
const CockpitPage = lazy(() => import("../pages/CockpitPage"));
const CommandCenterPage = lazy(() => import("../pages/CommandCenterPage"));
const LeadsPage = lazy(() => import("../pages/LeadsPage"));
const AnalyticsPage = lazy(() => import("../pages/AnalyticsPage"));
const AskPage = lazy(() => import("../pages/AskPage"));
const RunsPage = lazy(() => import("../pages/RunsPage"));
const RunDetailPage = lazy(() => import("../pages/RunDetailPage"));
const SchedulesPage = lazy(() => import("../pages/SchedulesPage"));
const ProfilesPage = lazy(() => import("../pages/ProfilesPage"));
const LoginPage = lazy(() => import("../pages/LoginPage"));
const NotFoundPage = lazy(() => import("../pages/NotFoundPage"));
const AdminSystemPage = lazy(() => import("../pages/admin/AdminSystemPage"));
const AdminUsersPage = lazy(() => import("../pages/admin/AdminUsersPage"));
const AdminSourcesPage = lazy(() => import("../pages/admin/AdminSourcesPage"));
const AdminSettingsPage = lazy(() => import("../pages/admin/AdminSettingsPage"));
const AdminAuditPage = lazy(() => import("../pages/admin/AdminAuditPage"));
const CompetitorsPage = lazy(() => import("../pages/CompetitorsPage"));
const PitchesPage = lazy(() => import("../pages/PitchesPage"));
const PipelinePage = lazy(() => import("../pages/PipelinePage"));
const ReportsPage = lazy(() => import("../pages/ReportsPage"));
const KnowledgePage = lazy(() => import("../pages/KnowledgePage"));
const InboxPage = lazy(() => import("../pages/InboxPage"));
const BillingPage = lazy(() => import("../pages/admin/BillingPage"));
const WorkspaceSettingsPage = lazy(() => import("../pages/admin/WorkspaceSettingsPage"));

function page(element: ReactNode) {
  return (
    <Suspense
      fallback={
        <Center h={320}>
          <Loader type="dots" />
        </Center>
      }
    >
      {element}
    </Suspense>
  );
}

const admin = (element: ReactNode) => page(<RequireAdmin>{element}</RequireAdmin>);
const platformAdmin = (element: ReactNode) => page(<RequirePlatformAdmin>{element}</RequirePlatformAdmin>);

export const router = createBrowserRouter([
  { path: "/login", element: page(<LoginPage />) },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: page(<CommandCenterPage />) },
      { path: "cockpit", element: page(<CockpitPage />) },
      { path: "leads", element: page(<LeadsPage />) },
      { path: "analytics", element: page(<AnalyticsPage />) },
      { path: "ask", element: page(<AskPage />) },
      { path: "competitors", element: page(<CompetitorsPage />) },
      { path: "pitches", element: page(<PitchesPage />) },
      { path: "pipeline", element: page(<PipelinePage />) },
      { path: "reports", element: page(<ReportsPage />) },
      { path: "knowledge", element: page(<KnowledgePage />) },
      { path: "inbox", element: page(<InboxPage />) },
      { path: "runs", element: page(<RunsPage />) },
      { path: "runs/:runId", element: page(<RunDetailPage />) },
      { path: "schedules", element: page(<SchedulesPage />) },
      { path: "profiles", element: page(<ProfilesPage />) },
      { path: "admin", element: platformAdmin(<AdminSystemPage />) },
      { path: "admin/users", element: admin(<AdminUsersPage />) },
      { path: "admin/sources", element: admin(<AdminSourcesPage />) },
      { path: "admin/settings", element: platformAdmin(<AdminSettingsPage />) },
      { path: "admin/audit", element: admin(<AdminAuditPage />) },
      { path: "admin/workspace", element: admin(<WorkspaceSettingsPage />) },
      { path: "admin/billing", element: admin(<BillingPage />) },
      { path: "*", element: page(<NotFoundPage />) },
    ],
  },
]);
