import api from './api';
export const deleteDraftReviews = (reviews, reason) => api.post('/performance/delete-drafts', { reviews, reason, confirmed:true });
