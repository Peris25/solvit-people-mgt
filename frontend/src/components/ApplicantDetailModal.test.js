import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ApplicantDetailModal from './ApplicantDetailModal';
jest.mock('../services/api', () => ({ eligibleCvUrl: id => `/eligible/${id}/cv`, ineligibleCvUrl: id => `/ineligible/${id}/cv` }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => { container=document.createElement('div'); document.body.appendChild(container); root=createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test.each(['eligible','ineligible'])('%s applicants without an available file have no download link', async mode => {
  await act(async () => root.render(<ApplicantDetailModal open mode={mode} data={{id:'synthetic',full_name:'Synthetic Applicant',has_cv:false,cv_path:'/stale/path.pdf',cv_filename:'old.pdf'}} />));
  expect(container.textContent).toContain('No CV attached');
  expect(container.querySelector('[data-testid="cv-download"]')).toBeNull();
});
test.each(['eligible','ineligible'])('%s applicants with an available CV retain the download link', async mode => {
  await act(async () => root.render(<ApplicantDetailModal open mode={mode} data={{id:'synthetic',full_name:'Synthetic Applicant',has_cv:true,cv_filename:'cv.pdf'}} />));
  expect(container.querySelector('[data-testid="cv-download"]').getAttribute('href')).toBe(`/${mode}/synthetic/cv`);
  expect(container.textContent).not.toContain('No CV attached');
});
