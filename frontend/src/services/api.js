import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${API}/api`,
  withCredentials: true,
});

// Global response interceptor — handle 401 auth errors gracefully so they
// don't bubble to React's error overlay as "Uncaught runtime errors".
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || '';
    if (status === 401) {
      // Session expired or not authenticated — clear hint, redirect to login.
      try {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('solvit_auth');
          // Avoid redirect loop on the login page itself
          if (!window.location.pathname.startsWith('/login')) {
            window.location.replace('/login');
          }
        }
      } catch (_) { /* ignore */ }
      return Promise.resolve({ data: null, status: 401, _silentAuth: true });
    }
    if (status >= 500) {
      // Server error — emit a custom event so a global toast/banner can show,
      // but don't bubble as an uncaught runtime error to React's overlay.
      try {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('solvit:server-error', {
            detail: {
              url,
              status,
              message: error?.response?.data?.detail || error?.message || 'Server error'
            }
          }));
        }
      } catch (_) { /* ignore */ }
      return Promise.resolve({ data: null, status, _serverError: true, error: error?.response?.data?.detail || error?.message });
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (email, password) => api.post('/auth/login', { email, password });
export const logout = () => api.post('/auth/logout');
export const getMe = () => api.get('/auth/me');

// Employees
export const getEmployees = (params) => api.get('/employees', { params });
export const getEmployee = (id) => api.get(`/employees/${id}`);
export const getEmployeeProfile = (id) => api.get(`/employees/${id}/profile`);
export const createEmployee = (data) => api.post('/employees', data);
export const updateEmployee = (id, data) => api.put(`/employees/${id}`, data);
export const transitionEmployee = (id, lifecycle_state) => api.post(`/employees/${id}/transition`, { lifecycle_state });
export const getKanban = () => api.get('/employees/kanban');
export const getEmployeeStats = () => api.get('/employees/stats');
export const seedDemoEmployees = () => api.post('/employees/seed-demo');

// Solvers
export const getSolvers = (params) => api.get('/solvers', { params });
export const getSolver = (id) => api.get(`/solvers/${id}`);
export const createSolver = (data) => api.post('/solvers', data);
export const updateSolver = (id, data) => api.put(`/solvers/${id}`, data);
export const activateSolver = (id) => api.post(`/solvers/${id}/activate`);
export const getSolverStats = () => api.get('/solvers/stats');

// Recruitment
export const getCandidates = (params) => api.get('/recruitment', { params });
export const createCandidate = (data) => api.post('/recruitment', data);
export const updateCandidate = (id, data) => api.put(`/recruitment/${id}`, data);
export const getRecruitmentPipeline = () => api.get('/recruitment/pipeline');
export const convertToEmployee = (id, data) => api.post(`/recruitment/${id}/convert-to-employee`, data);

// Onboarding
export const getEmployeeOnboarding = (id) => api.get(`/onboarding/employee/${id}`);
export const getSolverOnboarding = (id) => api.get(`/onboarding/solver/${id}`);
export const updateOnboardingTask = (id, data) => api.put(`/onboarding/tasks/${id}`, data);
export const getAllOnboarding = () => api.get('/onboarding/all');

// Performance
export const getReviews = (params) => api.get('/performance', { params });
export const createReview = (data) => api.post('/performance', data);
export const getReview = (id) => api.get(`/performance/${id}`);
export const updateReview = (id, data) => api.put(`/performance/${id}`, data);
export const getActiveCycle = () => api.get('/performance/active-cycle');
export const getNineBoxMatrix = (year) => api.get('/performance/nine-box/matrix', { params: { cycle_year: year } });
export const updateNineBoxPlacement = (employeeId, placement, cycle_year) => api.put(`/performance/nine-box/${employeeId}/placement`, { placement, cycle_year });

// Bulk
export const bulkTransitionEmployees = (employee_ids, lifecycle_state) => api.post('/employees/bulk-transition', { employee_ids, lifecycle_state });
export const bulkAssignTraining = (data) => api.post('/lnd/training/bulk-assign', data);

// Surveys quick-launch
export const launchQuickSurvey = (data) => api.post('/surveys/launch-quick', data);

// IDP
export const getIDP = (employee_id) => api.get(`/lnd/idp/${employee_id}`);
export const upsertIDP = (data) => api.post('/lnd/idp', data);

// Surveys
export const getSurveyWindows = () => api.get('/surveys/windows');
export const createSurveyWindow = (data) => api.post('/surveys/windows', data);
export const getSurveyQuestions = (type) => api.get(`/surveys/questions/${type}`);
export const submitSurveyResponse = (data) => api.post('/surveys/respond', data);
export const getSurveyResults = (id) => api.get(`/surveys/results/${id}`);

// Retention
export const getFlightRisks = (params) => api.get('/retention', { params });
export const calculateRisk = (id) => api.post(`/retention/calculate/${id}`);
export const getRiskSummary = () => api.get('/retention/risk-summary');
export const getExitInsights = () => api.get('/retention/exit-insights');
export const getStayInterviews = () => api.get('/retention/stay-interviews');
export const createStayInterview = (data) => api.post('/retention/stay-interviews', data);
export const updateStayInterview = (id, data) => api.put(`/retention/stay-interviews/${id}`, data);

// Settings — extras
export const sendTestEmail = (data) => api.post('/settings/email-test', data);

// LnD
export const getTrainingRequests = (params) => api.get('/lnd/training', { params });
export const createTrainingRequest = (data) => api.post('/lnd/training', data);
export const trainingDecision = (id, data) => api.put(`/lnd/training/${id}/decision`, data);
export const getSkillsMatrix = (empId) => api.get(`/lnd/skills-matrix/${empId}`);
export const updateSkillsMatrix = (empId, data) => api.post(`/lnd/skills-matrix/${empId}`, data);

// Compensation
export const getPayBands = () => api.get('/compensation/pay-bands');
export const updatePayBand = (id, data) => api.put(`/compensation/pay-bands/${id}`, data);
export const getPayBandAlerts = () => api.get('/compensation/pay-bands/alerts');
export const getBonusCalculator = (tier) => api.get('/compensation/bonus/calculator', { params: { tier } });
export const getGPGate = () => api.get('/compensation/gp-gate');

// Recognition
export const getRecognitions = (params) => api.get('/recognition', { params });
export const createPeerNomination = (data) => api.post('/recognition/peer-nomination', data);
export const getSolverAwards = () => api.get('/recognition/solver-awards');

// Budget
export const getBudgetSummary = () => api.get('/budget/summary');
export const getPeopleEnvelope = () => api.get('/budget/envelope');
export const submitGPRecord = (data) => api.post('/budget/gp-record', data);
export const submitForm28 = (data) => api.post('/budget/form-28', data);
export const getAllocations = () => api.get('/budget/allocations');
export const getAllocationSummary = () => api.get('/budget/allocations/summary');
export const createAllocation = (data) => api.post('/budget/allocations', data);
export const updateAllocation = (id, data) => api.put(`/budget/allocations/${id}`, data);
export const deleteAllocation = (id) => api.delete(`/budget/allocations/${id}`);

// Policies
export const getPolicies = () => api.get('/policies');
export const getPolicy = (id) => api.get(`/policies/${id}`);
export const createPolicy = (data) => api.post('/policies', data);
export const acknowledgePolicy = (id, data) => api.post(`/policies/${id}/acknowledge`, data);

// Disciplinary
export const getDisCases = (params) => api.get('/disciplinary', { params });
export const createDisCase = (data) => api.post('/disciplinary', data);
export const updateDisCase = (id, data) => api.put(`/disciplinary/${id}`, data);

// Leave
export const getLeaveRequests = (params) => api.get('/leave', { params });
export const createLeaveRequest = (data) => api.post('/leave', data);
export const leaveDecision = (id, data) => api.put(`/leave/${id}/decision`, data);
export const getLeaveBalances = (empId) => api.get(`/leave/balances/${empId}`);
export const getLeaveTypes = () => api.get('/leave/types');
export const getLeaveRollover = (empId) => api.get(`/leave/rollover/${empId}`);
export const getLeaveCalendar = (year, month) => api.get('/leave/calendar', { params: { year, month } });

// Calendar
export const getCalendarEvents = (daysAhead) => api.get('/calendar', { params: { days_ahead: daysAhead } });
export const createCalendarEvent = (data) => api.post('/calendar', data);

// Compliance
export const getStatutoryStatus = () => api.get('/compliance/statutory');
export const getPAYECalculator = (gross) => api.get('/compliance/paye-calculator', { params: { gross_salary: gross } });
export const getComplianceDeadlines = () => api.get('/compliance/deadlines');

// Settings
export const getSettings = () => api.get('/settings');
export const updateSettings = (data) => api.put('/settings', data);
export const getAuditLog = (params) => api.get('/settings/audit-log', { params });
export const resetDemoData = () => api.post('/settings/reset-demo-data');

// AI Agent
export const chatWithAgent = (data) => api.post('/ai-agent/chat', data);
export const runComplianceCheck = () => api.get('/ai-agent/compliance-check');
export const getAiSnapshot = () => api.get('/ai-agent/snapshot');
export const aiEmployeeStatus = (query) => api.get('/ai-agent/employee-status', { params: { query } });
export const executeAiAction = (actionId, paramsOverride = null) =>
  api.post(`/ai-agent/actions/${actionId}/execute`, paramsOverride ? { params_override: paramsOverride } : {});
export const cancelAiAction = (actionId) => api.post(`/ai-agent/actions/${actionId}/cancel`);
export const aiActionsAudit = () => api.get('/ai-agent/actions/audit');
export const getConversations = () => api.get('/ai-agent/conversations');

// Forms
export const getForms = () => api.get('/forms');
export const getFormSchema = (id) => api.get(`/forms/${id}`);
export const submitForm = (id, data) => api.post(`/forms/${id}/submit`, data);
export const startFormSubmission = (id, data) => api.post(`/forms/${id}/start`, data);
export const signFormStep = (subId, data) => api.post(`/forms/submissions/${subId}/sign`, data);
export const getMyFormTasks = () => api.get('/forms/my-tasks');

// Retention KPIs
export const getVoluntaryAttrition = () => api.get('/retention/voluntary-attrition');

// Performance KPIs
export const getTalentDensity = (cycle_year) => api.get('/performance/talent-density', { params: { cycle_year } });
export const getReviewPanel = (employee_id) => api.get(`/performance/review-panel/${employee_id}`);

// Access Matrix
export const getAccessMatrix = () => api.get('/access/matrix');
export const checkModuleAccess = (module_id) => api.get(`/access/check/${module_id}`);

// Masters Settings
export const listMastersSettings = () => api.get('/settings/masters');
export const getAllMastersSettings = () => api.get('/settings/masters/all');
export const getMastersSettings = (category) => api.get(`/settings/masters/${category}`);
export const updateMastersSettings = (category, values) => api.put(`/settings/masters/${category}`, { values });
export const resetMastersSettings = (category) => api.post(`/settings/masters/${category}/reset`);
export const getMastersAudit = ({ category, limit } = {}) => api.get('/settings/masters/audit/log', { params: { category, limit } });

// CSV exports — these return the URL; the caller opens it via window.location to use cookie auth.
export const csvExportUrl = (kind) => {
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  return `${base}/api/exports/${kind}.csv`;
};
export const downloadCSV = (kind) => { window.location.href = csvExportUrl(kind); };

// MD KPIs (Board-administered)
export const getMDKpis = () => api.get('/performance/md-kpis');

// Automation
export const getAutomationRules = () => api.get('/automation');
export const toggleRule = (ruleId) => api.put(`/automation/${ruleId}/toggle`);
export const getTasks = (params) => api.get('/automation/tasks', { params });
export const updateTask = (id, data) => api.put(`/automation/tasks/${id}`, data);
export const getNotifications = () => api.get('/automation/notifications');
export const markNotificationRead = (id) => api.put(`/automation/notifications/${id}/read`);

// Documents
export const getDocumentCategories = () => api.get('/documents/categories');
export const getEmployeeDocuments = (empId) => api.get(`/documents/employee/${empId}`);
export const uploadEmployeeDocument = (empId, formData) =>
  api.post(`/documents/employee/${empId}/upload`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
export const deleteEmployeeDocument = (docId) => api.delete(`/documents/${docId}`);
export const documentDownloadUrl = (docId) => {
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  return `${base}/api/documents/${docId}/download`;
};
export const getDocumentAuditLog = (params) => api.get('/documents/audit-log', { params });

// Data Import
export const dataImportTemplateUrl = (kind) => {
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  return `${base}/api/data-import/template/${kind}`;
};
export const validateImport = (formData) =>
  api.post('/data-import/validate', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
export const executeImport = (data) => api.post('/data-import/import', data);
export const getImportHistory = () => api.get('/data-import/history');
export const importHistoryDownloadUrl = (id) => {
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  return `${base}/api/data-import/history/${id}/download`;
};
export const downloadErrorReport = (rows) =>
  api.post('/data-import/error-report', { rows }, { responseType: 'blob' });

// Email Templates
export const listEmailTemplates = () => api.get('/email-templates');
export const getEmailTemplate = (key) => api.get(`/email-templates/${key}`);
export const updateEmailTemplate = (key, data) => api.put(`/email-templates/${key}`, data);
export const resetEmailTemplate = (key) => api.post(`/email-templates/${key}/reset`);
export const previewEmailTemplate = (key, merge_values = {}) => api.post(`/email-templates/${key}/preview`, { merge_values });

// Email Delivery
export const getEmailDelivery = () => api.get('/email-delivery');
export const updateEmailDeliveryMode = (mode, data) => api.put(`/email-delivery/${mode}`, data);
export const switchEmailDeliveryMode = (mode) => api.post('/email-delivery/switch', { mode });
export const sendEmailDeliveryTest = (to) => api.post('/email-delivery/test-send', { to });
export const getEmailDeliveryAudit = () => api.get('/email-delivery/audit');

// Onboarding Tour
export const getMyTour = () => api.get('/onboarding-tour/me');
export const completeTour = (skipped = false) => api.post('/onboarding-tour/complete', { skipped });
export const replayTour = () => api.post('/onboarding-tour/replay');
export const getTourConfig = () => api.get('/onboarding-tour/config');
export const updateTourConfig = (data) => api.put('/onboarding-tour/config', data);
export const resetTourForUser = (userId) => api.post(`/onboarding-tour/reset/${userId}`);
export const getTourReport = () => api.get('/onboarding-tour/report');

export default api;
