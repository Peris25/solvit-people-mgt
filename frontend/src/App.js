import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Employees from './pages/Employees';
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
import Forms from './pages/Forms';
import EmployeeProfile from './pages/EmployeeProfile';
import MyTasks from './pages/MyTasks';
import ErrorToast from './components/ErrorToast';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ErrorToast />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="employees" element={<Employees />} />
            <Route path="employees/:id" element={<EmployeeProfile />} />
            <Route path="solvers" element={<Solvers />} />
            <Route path="recruitment" element={<Recruitment />} />
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="performance" element={<Performance />} />
            <Route path="surveys" element={<Surveys />} />
            <Route path="retention" element={<Retention />} />
            <Route path="lnd" element={<LnD />} />
            <Route path="projects" element={<Projects />} />
            <Route path="compensation" element={<Compensation />} />
            <Route path="recognition" element={<Recognition />} />
            <Route path="budget" element={<Budget />} />
            <Route path="policies" element={<Policies />} />
            <Route path="disciplinary" element={<Disciplinary />} />
            <Route path="calendar" element={<Calendar />} />
            <Route path="leave" element={<Leave />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="settings" element={<Settings />} />
            <Route path="forms" element={<Forms />} />
            <Route path="my-tasks" element={<MyTasks />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
