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
    if (error?.response?.status === 401) {
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
      // Resolve as a benign empty response instead of rejecting,
      // so individual components don't show error overlays.
      return Promise.resolve({ data: null, status: 401, _silentAuth: true });
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
export const getIDP = (empId) => api.get(`/lnd/idp/${empId}`);
export const saveIDP = (data) => api.post('/lnd/idp', data);
export const getTrainingRequests = (params) => api.get('/lnd/training', { params });
export const createTrainingRequest = (data) => api.post('/lnd/training', data);
export const trainingDecision = (id, data) => api.put(`/lnd/training/${id}/decision`, data);

// Compensation
export const getPayBands = () => api.get('/compensation/pay-bands');
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
export const getConversations = () => api.get('/ai-agent/conversations');

// Forms
export const getForms = () => api.get('/forms');
export const getFormSchema = (id) => api.get(`/forms/${id}`);
export const submitForm = (id, data) => api.post(`/forms/${id}/submit`, data);

// Automation
export const getAutomationRules = () => api.get('/automation');
export const toggleRule = (ruleId) => api.put(`/automation/${ruleId}/toggle`);
export const getTasks = (params) => api.get('/automation/tasks', { params });
export const updateTask = (id, data) => api.put(`/automation/tasks/${id}`, data);
export const getNotifications = () => api.get('/automation/notifications');
export const markNotificationRead = (id) => api.put(`/automation/notifications/${id}/read`);

export default api;
