import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireRole } from '@/auth';
import { RequireAuthOrHome } from '@/features/home/RequireAuthOrHome';
import { AppLayout } from '@/shell/AppLayout';
import { Login } from '@/pages/Login';
import { CaseRegister, CaseDetailPage } from '@/features/cases';
import { InstitutionList, Institution360 } from '@/features/institutions';
import type { Role } from '@/lib/constants';
import { DEMO_MODE } from '@/lib/env';

const HomePage = lazy(() => import('@/features/home/HomePage'));
const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));

const ReportsPage = lazy(() => import('@/features/reports/ReportsPage'));

const AdminPage = lazy(() => import('@/features/admin/AdminPage'));

const ImportPage = lazy(() => import('@/features/import/ImportPage'));

const EvaluationPage = lazy(() => import('@/features/evaluation/EvaluationPage'));

const NewCasePage = lazy(() => import('@/features/intake/NewCasePage'));
const ReviewPage = lazy(() => import('@/features/review/ReviewPage'));
const PreActionPage = lazy(() => import('@/features/preaction/PreActionPage'));
const ClearanceInbox = lazy(() => import('@/features/clearances/ClearanceInbox'));
const CoordinationInbox = lazy(() => import('@/features/coordination/CoordinationInbox'));
const LinkCompare = lazy(() => import('@/features/coordination/LinkCompare'));

// Hidden component-kit route, not linked in the nav.
const Kit = lazy(() => import('@/pages/Kit'));

// Roles allowed on working screens (SENIOR_MGMT is read-only oversight).
const WORK: Role[] = ['PGRC_OFFICER', 'RB_OFFICER', 'APPROVAL_OFFICER', 'VIGILANCE_OFFICER', 'RO_OFFICER', 'BUREAU_HEAD', 'ADMIN'];

/**
 * Route registry: one line per route.
 * Guard groups wrap whole blocks; each block keeps its <Route path=...> lines.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Public Home (explanatory page, owner decision 2026-11-02): outside the app shell, no sign-in needed. */}
      <Route path="/home" element={<Suspense fallback={null}><HomePage /></Suspense>} />
      {/* Hidden component-kit route: only mounted in DEMO_MODE; otherwise falls through to the catch-all redirect. */}
      {DEMO_MODE && <Route path="/_kit" element={<Suspense fallback={null}><Kit /></Suspense>} />}
      <Route element={<RequireAuthOrHome />}>
        <Route element={<AppLayout />}>
          {/* --- routes --- */}
          <Route path="/" element={<Suspense fallback={null}><DashboardPage /></Suspense>} />
          <Route path="/cases" element={<CaseRegister />} />
          <Route path="/cases/:id" element={<CaseDetailPage />} />
          <Route path="/institutions" element={<InstitutionList />} />
          <Route path="/institutions/:id" element={<Institution360 />} />
          <Route path="/institutions/:id/pre-action/:actionId" element={<Suspense fallback={null}><PreActionPage /></Suspense>} />
          <Route path="/reports" element={<Suspense fallback={null}><ReportsPage /></Suspense>} />
          <Route path="/evaluation" element={<Suspense fallback={null}><EvaluationPage /></Suspense>} />
          {/* officers, heads and admin only */}
          <Route element={<RequireRole roles={WORK} />}>
            <Route path="/cases/new" element={<Suspense fallback={null}><NewCasePage /></Suspense>} />
            <Route path="/coordination" element={<Suspense fallback={null}><CoordinationInbox /></Suspense>} />
            <Route path="/coordination/:linkId" element={<Suspense fallback={null}><LinkCompare /></Suspense>} />
            <Route path="/clearances" element={<Suspense fallback={null}><ClearanceInbox /></Suspense>} />
            <Route path="/review" element={<Suspense fallback={null}><ReviewPage /></Suspense>} />
            <Route path="/import" element={<Suspense fallback={null}><ImportPage /></Suspense>} />
          </Route>
          {/* admin only */}
          <Route element={<RequireRole roles={['ADMIN']} />}>
            <Route path="/admin" element={<Suspense fallback={null}><AdminPage /></Suspense>} />
          </Route>
          {/* --- end routes --- */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
