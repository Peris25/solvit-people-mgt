import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import TalentDensityCard from './TalentDensityCard';
global.IS_REACT_ACT_ENVIRONMENT=true;
test('shows the current weights and weighted component contributions',async()=>{
  const container=document.createElement('div');document.body.appendChild(container);const root=createRoot(container);
  try {
    await act(async()=>root.render(<TalentDensityCard data={{score_pct:73.2,components:{primary_stars_core_pct:80,secondary_values_avg_pct:60,alignment_survey_pct:76}}}/>));
    expect(container.textContent).toContain('50% weight');expect(container.textContent).toContain('30% weight');expect(container.textContent).toContain('20% weight');
    expect(container.textContent).toContain('73.2%');expect(container.textContent).toContain('40.00 points');expect(container.textContent).toContain('18.00 points');expect(container.textContent).toContain('15.20 points');
    await act(async()=>root.render(<TalentDensityCard data={{score_pct:null,components:{}}}/>));
    expect(container.querySelector('.talent-density-total strong').textContent).toBe('Awaiting data');
  }finally{await act(async()=>root.unmount());container.remove();}
});
