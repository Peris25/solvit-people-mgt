import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import EmployeeDocuments from '../components/EmployeeDocuments';
import EmployeePicker from '../components/EmployeePicker';

export default function Documents() {
  const { user } = useAuth();
  const [selected, setSelected] = useState(null);
  const key = `${user?.id}:${user?.role}`;
  const [selectionKey, setSelectionKey] = useState(key);
  useEffect(() => { setSelected(null); setSelectionKey(key); }, [key]);
  const canManage = ['hr_admin', 'hr_manager'].includes(user?.role);
  const employee = selectionKey === key ? selected : null;
  return <div data-testid="documents-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
    <h1 style={{ fontFamily: 'Barlow', fontSize: '32px', marginBottom: '6px' }}>Documents</h1>
    <p>Private employee documents. Company policies remain in the separate Policy Library.</p>
    {canManage && <section style={{ background: '#fff', padding: '18px', margin: '18px 0', maxWidth: '700px' }}>
      <h2 style={{ fontSize: '16px' }}>HR document assignment</h2><p>Select the saved employee record to view or upload assigned documents.</p>
      <EmployeePicker value={employee?.id || ''} onChange={record => { setSelected(record); setSelectionKey(key); }} placeholder="Choose an employee" testId="document-employee-picker" />
      {employee && <p>Managing: {employee.full_name} <button onClick={() => setSelected(null)}>My documents</button></p>}
    </section>}
    <EmployeeDocuments key={`${key}:${employee?.id || 'self'}`} employeeId={employee?.id} user={user} />
  </div>;
}
