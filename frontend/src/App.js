import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/RoleDashboard';
import Employees from './pages/Employees';
import Organogram from './pages/Organogram';
import Solvers from './pages/Solvers';
import Recruitment from './pages/Recruitment';
import Onboarding from './pages/Onboarding';
import Performance from './pages/Performance';
import Surveys from './pages/Surveys';
import Retention from './pages/Retention';
import LnD from './pages/LnD';
import Projects from './pages/Projects';
import Compensation from './pages/Compensation';
import Recognition from './pages/Recognition';
import Budget from './pages/Budget';
import Policies from './pages/Policies';
import Disciplinary from './pages/Disciplinary';
import Calendar from './pages/Calendar';
import Leave from './pages/Leave';
import Compliance from './pages/Compliance';
import Settings from './pages/Settings';
import MastersSettings from './pages/MastersSettings';
import Forms from './pages/Forms';
import EmployeeProfile from './pages/EmployeeProfile';
import MyTasks from './pages/MyTasks';
import DataImport from './pages/DataImport';
import RolesPermissions from './pages/RolesPermissions';
import ErrorToast from './components/ErrorToast';
import AccessGate from './components/AccessGate';

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <ErrorToast />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="employees" element={<Employees />} />
            <Route path="organogram" element={<Organogram />} />
            <Route path="employees/:id" element={<EmployeeProfile />} />
            <Route path="solvers" element={<Solvers />} />
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
            <Route path="masters" element={<MastersSettings />} />
            <Route path="forms" element={<Forms />} />
            <Route path="my-tasks" element={<MyTasks />} />
            <Route path="data-import" element={<DataImport />} />
            <Route path="roles-permissions" element={<RolesPermissions />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
