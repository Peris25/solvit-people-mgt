import {actionErrorMessage} from './actionFeedback';
test('server validation identifies fields without echoing submitted values',()=>{
 const error={response:{status:422,data:{detail:[{loc:['body','employee_id'],type:'missing',input:'PRIVATE_VALUE'},{loc:['body','start_date'],type:'date_parsing',input:'PRIVATE_DATE'}]}}};
 expect(actionErrorMessage(error)).toBe('Complete employee id. Check start date.');expect(actionErrorMessage(error)).not.toContain('PRIVATE');
});
test('network failures give a safe retry instruction',()=>expect(actionErrorMessage({})).toContain('check the record status before retrying'));
