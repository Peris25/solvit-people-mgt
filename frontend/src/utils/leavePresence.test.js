import {leaveTiming,nairobiDate} from './leaveDisplay';

test('approved absences include both boundary days, excluding pending and finished leave',()=>{
  const row={status:'Approved',start_date:'2026-11-24',end_date:'2026-11-25'};
  expect(leaveTiming(row,'2026-11-24')).toBe('On leave now');
  expect(leaveTiming(row,'2026-11-25')).toBe('On leave now');
  expect(leaveTiming(row,'2026-11-23')).toBe('Upcoming leave');
  expect(leaveTiming(row,'2026-11-26')).toBeNull();
  expect(leaveTiming({...row,status:'Pending_HR'},'2026-11-24')).toBeNull();
  expect(leaveTiming({...row,end_date:null},'2026-11-24')).toBeNull();
});

test('Nairobi dates roll over at 21:00 UTC',()=>{
  expect(nairobiDate(new Date('2026-11-23T20:59:59Z'))).toBe('2026-11-23');
  expect(nairobiDate(new Date('2026-11-23T21:00:00Z'))).toBe('2026-11-24');
});
