import React,{useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {useLocation} from 'react-router-dom';
import {fieldProblem} from '../utils/actionFeedback';
import './ActionFeedback.css';

export default function FormValidationFeedback(){
  const [form,setForm]=useState(null),[,setRevision]=useState(0);
  const location=useLocation();
  useEffect(()=>{setForm(null);},[location.key]);
  useEffect(()=>{
    const invalid=event=>{
      const control=event.target;
      if(!control.form||!control.willValidate)return;
      event.preventDefault();setForm(control.form);setRevision(value=>value+1);
      queueMicrotask(()=>{if(control.form?.isConnected){const first=[...control.form.elements].find(field=>field.willValidate&&!field.validity.valid);first?.focus();}});
    };
    const changed=()=>setRevision(value=>value+1);
    const submitted=event=>{if(event.target instanceof HTMLFormElement)setForm(null);};
    document.addEventListener('invalid',invalid,true);
    document.addEventListener('input',changed,true);document.addEventListener('change',changed,true);
    document.addEventListener('submit',submitted,true);
    return()=>{document.removeEventListener('invalid',invalid,true);document.removeEventListener('input',changed,true);document.removeEventListener('change',changed,true);document.removeEventListener('submit',submitted,true);};
  },[]);
  const controls=form?.isConnected?[...form.elements].filter(control=>control.willValidate&&!control.validity.valid):[];
  const seen=new Set();
  const fields=controls.filter(control=>{const key=control.type==='radio'?control.name:control;if(seen.has(key))return false;seen.add(key);return true;});
  if(!form?.isConnected||!fields.length)return null;
  return createPortal(<section className="form-validation-summary" role="alert" aria-label="Information needed before submitting"><strong>Please complete the following before submitting:</strong><ul>{fields.map((control,index)=><li key={index}><button type="button" onClick={()=>{control.focus();control.scrollIntoView?.({block:'center',behavior:'smooth'});}}>{fieldProblem(control)}</button></li>)}</ul></section>,form);
}
