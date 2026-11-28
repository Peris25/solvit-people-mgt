const labelText=node=>node.nodeType===3?node.textContent:node.nodeType===1&&['INPUT','SELECT','TEXTAREA','BUTTON','SCRIPT','STYLE'].includes(node.tagName)?'':[...node.childNodes].map(labelText).join(' ');
export function fieldLabel(control){
  const legend=control.type==='radio'?control.closest('fieldset')?.querySelector('legend'):null;
  const label=legend?.textContent||control.getAttribute('aria-label')||[...(control.labels||[])].map(node=>labelText(node).trim()).find(Boolean)||control.name?.replaceAll('_',' ')||'This field';
  return label.replace(/\s+/g,' ').replace(/\s*\*\s*$/,'').trim();
}
export function fieldProblem(control){
  const name=fieldLabel(control),v=control.validity;
  if(v.valueMissing)return control.type==='checkbox'?`Confirm ${name} to continue.`:control.type==='file'?`Choose a file for ${name}.`:`Complete ${name}.`;
  if(v.typeMismatch)return `Enter a valid ${control.type==='email'?'email address':control.type==='url'?'web address':name} for ${name}.`;
  if(v.rangeUnderflow)return `${name} must be at least ${control.min}.`;
  if(v.rangeOverflow)return `${name} must be no more than ${control.max}.`;
  if(v.tooShort)return `${name} needs at least ${control.minLength} characters.`;
  if(v.tooLong)return `${name} must be no more than ${control.maxLength} characters.`;
  if(v.badInput||v.stepMismatch)return `Enter a valid value for ${name}.`;
  return `${name}: ${control.validationMessage||'Check this value before continuing.'}`;
}
export function actionErrorMessage(error){
  const status=error?.response?.status;
  const detail=error?.response?.data?.detail;
  // Only explicitly public string errors are displayed; never serialize request data.
  if(typeof detail==='string'&&detail.trim()&&status<500)return detail+(status===403?' Ask HR or your administrator to check your access.':'');
  if(Array.isArray(detail)){
    const fields=[...new Set(detail.map(issue=>{
      const name=Array.isArray(issue.loc)?issue.loc.filter(part=>typeof part==='string'&&!['body','query','path'].includes(part)&&/^[a-z_]{1,40}$/i.test(part)).map(part=>part.replaceAll('_',' ')).join(' / '):'';
      return name?`${String(issue.type||'').includes('missing')?'Complete':'Check'} ${name}.`:'';
    }).filter(Boolean))].slice(0,10);
    return fields.length?fields.join(' '):'Some information is missing or invalid. Check the form details and try again.';
  }
  if(status===403)return 'Your account cannot perform this action. Ask HR or your administrator to check your access.';
  if(status===404)return 'This record is no longer available. Refresh the page and check before trying again.';
  if(status===409)return 'This record has changed or a required step is incomplete. Refresh it and check the latest status before retrying.';
  if(status===429)return 'Too many attempts. Wait a moment before trying again.';
  if(!error?.response)return 'Unable to reach the server. Check your connection. If you were saving or submitting, check the record status before retrying.';
  return 'The action could not be confirmed. Check the record status before retrying to avoid a duplicate.';
}
