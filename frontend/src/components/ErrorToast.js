import React,{useEffect,useState} from 'react';
export default function ErrorToast(){
  const [errors,setErrors]=useState([]);
  useEffect(()=>{
    const handler=event=>{
      const message=typeof event.detail?.message==='string'?event.detail.message:'The action could not be confirmed. Check the record status before retrying.';
      setErrors(previous=>[...previous.filter(item=>item.message!==message),{id:Date.now()+Math.random(),message}].slice(-3));
    };
    window.addEventListener('solvit:server-error',handler);
    return()=>window.removeEventListener('solvit:server-error',handler);
  },[]);
  if(!errors.length)return null;
  return <div data-testid="error-toast-stack" style={{position:'fixed',bottom:20,right:20,zIndex:9999,display:'flex',flexDirection:'column',gap:8,maxWidth:'min(420px,calc(100vw - 40px))',maxHeight:'70vh',overflowY:'auto'}}>{errors.map(error=><div key={error.id} role="alert" style={{background:'var(--portal-card,#fff)',border:'1px solid #b45309',borderRadius:10,color:'var(--portal-text,#253247)',padding:16,boxShadow:'0 4px 16px rgba(0,0,0,0.12)'}}><div style={{display:'flex',gap:12,alignItems:'flex-start'}}><div><strong>Action needs attention</strong><p style={{margin:'8px 0 0',fontSize:14,lineHeight:1.5}}>{error.message}</p></div><button type="button" aria-label="Dismiss action message" onClick={()=>setErrors(previous=>previous.filter(item=>item.id!==error.id))} style={{border:0,background:'transparent',color:'inherit',minWidth:44,minHeight:44,cursor:'pointer'}}>Close</button></div></div>)}</div>;
}
