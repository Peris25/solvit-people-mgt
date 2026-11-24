import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getMyTaskQueue } from '../services/api';

export default function useMyTaskQueue() {
  const { user } = useAuth();
  const accountKey=`${user?.id||''}:${user?.role||''}`;
  const [attempt,setAttempt]=useState(0);
  const [state,setState]=useState({data:null,loading:true,error:''});
  const reload=useCallback(()=>setAttempt(value=>value+1),[]);
  useEffect(()=>{
    let active=true;
    setState({accountKey,data:null,loading:true,error:''});
    (async()=>{
      try {
        const response=await getMyTaskQueue();
        if(!Array.isArray(response?.data?.items)||!Array.isArray(response.data.errors))throw new Error('Invalid task response');
        if(active)setState({accountKey,data:response.data,loading:false,error:''});
      }catch(error){if(active)setState({accountKey,data:null,loading:false,error:'Your task list could not load. Please retry.'});}
    })();
    return()=>{active=false;};
  },[accountKey,attempt]);
  useEffect(()=>{window.addEventListener('focus',reload);return()=>window.removeEventListener('focus',reload);},[reload]);
  const current=state.accountKey===accountKey?state:{data:null,loading:true,error:''};
  return {...current,count:current.error||current.data?.errors?.length?null:current.data?.count??null,reload};
}
