import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import { ForgotPassword, ResetPassword } from './pages/PasswordRecovery';
const Dashboard = lazy(() => import('./pages/RoleDashboard'));
const Employees = lazy(() => import('./pages/Employees'));
const Organogram = lazy(() => import('./pages/Organogram'));
const StaffDirectory = lazy(() => import('./pages/StaffDirectory'));
const Solvers = lazy(() => import('./pages/Solvers'));
const SolverApplicantInbox = lazy(() => import('./pages/SolverApplicantInbox'));
const Recruitment = lazy(() => import('./pages/Recruitment'));
const Onboarding = lazy(() => import('./pages/Onboarding'));
const Performance = lazy(() => import('./pages/Performance'));
const Surveys = lazy(() => import('./pages/Surveys'));
const Retention = lazy(() => import('./pages/Retention'));
const LnD = lazy(() => import('./pages/LnD'));
const Projects = lazy(() => import('./pages/Projects'));
const Compensation = lazy(() => import('./pages/Compensation'));
const Recognition = lazy(() => import('./pages/Recognition'));
const Budget = lazy(() => import('./pages/Budget'));
const Policies = lazy(() => import('./pages/Policies'));
const Disciplinary = lazy(() => import('./pages/Disciplinary'));
const Calendar = lazy(() => import('./pages/Calendar'));
const Benefits = lazy(() => import('./pages/Benefits'));
const Reporting = lazy(() => import('./pages/Reporting'));
const Leave = lazy(() => import('./pages/Leave'));
const Compliance = lazy(() => import('./pages/Compliance'));
const Settings = lazy(() => import('./pages/Settings'));
const MastersSettings = lazy(() => import('./pages/MastersSettings'));
const Forms = lazy(() => import('./pages/Forms'));
const EmployeeProfile = lazy(() => import('./pages/EmployeeProfile'));
const MyTasks = lazy(() => import('./pages/MyTasks'));
const DataImport = lazy(() => import('./pages/DataImport'));
const RolesPermissions = lazy(() => import('./pages/RolesPermissions'));
import ErrorToast from './components/ErrorToast';
import AccessGate from './components/AccessGate';
import SolverIntakeAccess from './components/SolverIntakeAccess';
const SolverRequisitions = lazy(() => import('./pages/SolverRequisitions'));
const IneligibleApplicants = lazy(() => import('./pages/IneligibleApplicants'));
const EligibleSolvers = lazy(() => import('./pages/EligibleSolvers'));
const PublicSolverApply = lazy(() => import('./pages/PublicSolverApply'));
const Notifications = lazy(() => import('./pages/Notifications'));
const Documents = lazy(() => import('./pages/Documents'));
import MfaSecurity from './pages/MfaSecurity';
import { NotificationProvider } from './context/NotificationContext';
import PublicSolverAssessment from './pages/PublicSolverAssessment';

export default function App() {
  return <BrowserRouter><Routes>
    <Route path="/solver-assessments" element={<PublicSolverAssessment />} />
    <Route path="/*" element={<Portal />} />
  </Routes></BrowserRouter>;
}

function Portal() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <NotificationProvider>
          <ErrorToast />
        <Suspense fallback={<div role="status" style={{ padding: '24px' }}>Loading page...</div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/apply/:rid" element={<PublicSolverApply />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="employees" element={<Employees />} />
            <Route path="organogram" element={<Organogram />} />
            <Route path="staff-directory" element={<StaffDirectory />} />
            <Route path="employees/:id" element={<EmployeeProfile />} />
            <Route path="my-profile" element={<EmployeeProfile selfService />} />
            <Route path="documents" element={<Documents />} />
            <Route path="benefits" element={<Benefits />} />
            <Route path="reporting" element={<Reporting />} />
            <Route path="solvers" element={<Solvers />} />
            <Route path="solver-assessment-applications" element={<SolverApplicantInbox />} />
            <Route path="solver-requisitions" element={<SolverIntakeAccess><SolverRequisitions /></SolverIntakeAccess>} />
            <Route path="solver-eligible" element={<SolverIntakeAccess><EligibleSolvers /></SolverIntakeAccess>} />
            <Route path="solver-ineligible" element={<SolverIntakeAccess><IneligibleApplicants /></SolverIntakeAccess>} />
            <Route path="recruitment" element={<Recruitment />} />
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="performance" element={<Performance />} />
            <Route path="surveys" element={<Surveys />} />
            <Route path="retention" element={<Retention />} />
            <Route path="lnd" element={<LnD />} />
            <Route path="projects" element={<Projects />} />
            <Route path="compensation" element={<AccessGate module="M10"><Compensation /></AccessGate>} />
            <Route path="recognition" element={<AccessGate module="M11"><Recognition /></AccessGate>} />
            <Route path="budget" element={<AccessGate module="M12"><Budget /></AccessGate>} />
            <Route path="policies" element={<AccessGate module="M13"><Policies /></AccessGate>} />
            <Route path="disciplinary" element={<AccessGate module="M14"><Disciplinary /></AccessGate>} />
            <Route path="calendar" element={<AccessGate module="M15"><Calendar /></AccessGate>} />
            <Route path="leave" element={<AccessGate module="M18"><Leave /></AccessGate>} />
            <Route path="compliance" element={<AccessGate module="M19"><Compliance /></AccessGate>} />
            <Route path="settings" element={<Settings />} />
            <Route path="account-security" element={<MfaSecurity />} />
            <Route path="masters" element={<MastersSettings />} />
            <Route path="forms" element={<Forms />} />
            <Route path="my-tasks" element={<MyTasks />} />
            <Route path="data-import" element={<DataImport />} />
            <Route path="roles-permissions" element={<RolesPermissions />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
        </Suspense>
        </NotificationProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
