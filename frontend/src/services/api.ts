import type { ApiKeyCreated, ApiKeyInfo, BackendModelsResponse, DocumentInfo, JobInfo, OrkgAskResult, OrkgConnectResult, OrkgSearchResult, ReviewCreatePayload, ReviewOut, ReviewSummary, StreamDone, PreviewOut, SparqlResult } from '@/types';

export const API_BASE_URL=(import.meta.env.VITE_API_BASE_URL||'https://litreview-web.onrender.com').replace(/\/$/,'');
const KEY_STORAGE='research-gen.api-key';
export const getApiKey=()=>localStorage.getItem(KEY_STORAGE)||import.meta.env.VITE_API_KEY||'';
export const setApiKey=(key:string)=>localStorage.setItem(KEY_STORAGE,key.trim());
export const clearApiKey=()=>localStorage.removeItem(KEY_STORAGE);

// Silently provision an API key on first visit so the user never has to think about
// keys. Uploads and review generation need one; the picker (GET /models) is public.
// A module-level in-flight promise makes this a singleton: concurrent callers (page
// load + an eager Generate click) share ONE request and one key, instead of racing to
// create two — the race that left the first generate half-initialised.
let _keyInFlight:Promise<string>|null=null;
export function ensureApiKey():Promise<string>{
 const existing=getApiKey();
 if(existing)return Promise.resolve(existing);
 if(_keyInFlight)return _keyInFlight;
 _keyInFlight=(async()=>{
  const email=`web-${crypto.randomUUID().slice(0,8)}@research-gen.app`;
  const created=await createApiKey(email,'web-ui');
  setApiKey(created.api_key);
  return created.api_key;
 })().catch((e)=>{_keyInFlight=null;throw e;}); // reset so a failed provision can retry
 return _keyInFlight;
}

function authHeaders(extra:Record<string,string>={}) {
 const key=getApiKey();
 return {Accept:'application/json',...(key?{'X-API-Key':key}:{}),...extra};
}
async function errorOf(r:Response):Promise<never>{
 let msg=`Le backend a renvoyé une erreur (${r.status}).`;
 try {
  const b=await r.json();
  msg=b?.error?.message||b?.detail||msg;
  if(b?.error?.details?.length) msg+=' '+b.error.details.map((d:any)=>d.message||d.field||'').filter(Boolean).join(' ');
 } catch { const t=await r.text().catch(()=> ''); if(t) msg+=' '+t.slice(0,300); }
 throw new Error(msg);
}
async function request<T>(path:string, init:RequestInit={}):Promise<T>{
 const r=await fetch(`${API_BASE_URL}${path}`,{...init,headers:{...authHeaders(),...(init.headers as Record<string,string>|undefined)}});
 if(!r.ok)return errorOf(r); return r.json() as Promise<T>;
}
export const health=()=>fetch(`${API_BASE_URL}/healthz`).then(async r=>({ok:r.ok,data:await r.json().catch(()=>({}))}));
export const listModels=()=>request<BackendModelsResponse>('/api/v1/models');
export async function uploadDocument(file:File){
 const f=new FormData(); f.append('file',file,file.name);
 const ctrl=new AbortController();
 const timer=setTimeout(()=>ctrl.abort(),180000); // scanned PDFs are OCR'd server-side
 let r:Response;
 try {
  r=await fetch(`${API_BASE_URL}/api/v1/documents`,{method:'POST',headers:authHeaders(),body:f,signal:ctrl.signal});
 } catch {
  throw new Error(ctrl.signal.aborted
   ?'Upload took too long (large or scanned file). Please try again.'
   :'Could not reach the server. Check your connection and try again.');
 } finally { clearTimeout(timer); }
 if(!r.ok)return errorOf(r); return r.json() as Promise<DocumentInfo>;
}
export const getDocument=(id:string)=>request<DocumentInfo>(`/api/v1/documents/${encodeURIComponent(id)}`);
export async function createReview(payload:ReviewCreatePayload){
 return request<JobInfo>('/api/v1/reviews',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(payload)});
}
export const getJob=(id:string)=>request<JobInfo>(`/api/v1/reviews/jobs/${encodeURIComponent(id)}`);
export async function pollJob(id:string, onProgress?:(j:JobInfo)=>void, timeout=10*60*1000){
 const start=Date.now(); let delay=700;
 while(Date.now()-start<timeout){ const j=await getJob(id); onProgress?.(j); if(j.status==='succeeded'||j.status==='failed'){if(j.status==='failed')throw new Error(j.error||'Le job a échoué.');return j;} await new Promise(r=>setTimeout(r,delay)); delay=Math.min(2500,delay+300); }
 throw new Error('Le délai d’attente du job est dépassé.');
}
export const getReview=(id:string)=>request<ReviewOut>(`/api/v1/reviews/${encodeURIComponent(id)}`);
export const listReviews=(q?:string)=>request<ReviewSummary[]>(`/api/v1/reviews${q&&q.trim()?`?q=${encodeURIComponent(q.trim())}`:''}`);
export const renameReview=(id:string,topic:string)=>request<ReviewSummary>(`/api/v1/reviews/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic})});
export async function deleteReview(id:string){const r=await fetch(`${API_BASE_URL}/api/v1/reviews/${encodeURIComponent(id)}`,{method:'DELETE',headers:authHeaders()}); if(!r.ok&&r.status!==204)return errorOf(r);}

// ChatGPT-style live generation over Server-Sent Events. Streams tokens to onToken,
// resolves via onDone with the persisted review id, or reports onError.
export async function streamReview(
 payload:ReviewCreatePayload,
 handlers:{onToken:(t:string)=>void;onDone:(d:StreamDone)=>void;onError:(e:Error)=>void;signal?:AbortSignal},
):Promise<void>{
 let r:Response;
 try{
  r=await fetch(`${API_BASE_URL}/api/v1/reviews/stream`,{method:'POST',headers:{...authHeaders(),'Content-Type':'application/json'},body:JSON.stringify(payload),signal:handlers.signal});
 }catch{ handlers.onError(new Error('Could not reach the server. Check your connection and try again.')); return; }
 if(!r.ok||!r.body){ let msg=`The backend returned an error (${r.status}).`; try{const b=await r.json();msg=b?.error?.message||b?.detail||msg;}catch{/* keep default */} handlers.onError(new Error(msg)); return; }
 const reader=r.body.getReader(); const dec=new TextDecoder(); let buf='';
 for(;;){
  const {value,done}=await reader.read(); if(done)break;
  buf+=dec.decode(value,{stream:true});
  let idx:number;
  while((idx=buf.indexOf('\n\n'))>=0){
   const block=buf.slice(0,idx); buf=buf.slice(idx+2);
   const line=block.split('\n').find((l)=>l.startsWith('data:'));
   if(!line)continue;
   let evt:{type:string;text?:string;message?:string;[k:string]:unknown};
   try{evt=JSON.parse(line.slice(5).trim());}catch{continue;}
   if(evt.type==='token'&&typeof evt.text==='string')handlers.onToken(evt.text);
   else if(evt.type==='done')handlers.onDone(evt as unknown as StreamDone);
   else if(evt.type==='error')handlers.onError(new Error(evt.message||'Generation failed.'));
  }
 }
}
export const getPreview=(id:string)=>request<PreviewOut>(`/api/v1/reviews/${encodeURIComponent(id)}/preview?format=html`);
export async function exportReview(id:string,format:'md'|'docx'|'pdf'){
 const r=await fetch(`${API_BASE_URL}/api/v1/reviews/${encodeURIComponent(id)}/export?format=${format}`,{headers:authHeaders()});
 if(!r.ok)return errorOf(r);
 if(r.status===202){ const j=await r.json() as JobInfo; const done=await pollJob(j.id); const url=done.result.download_url as string|undefined; if(!url)throw new Error('Le backend n’a pas fourni d’URL de téléchargement.'); const d=await fetch(url); if(!d.ok)throw new Error(`Téléchargement impossible (${d.status}).`); return {blob:await d.blob(),filename:`review.${format}`};}
 const disp=r.headers.get('Content-Disposition')||''; const m=disp.match(/filename="?([^"]+)"?/i);
 return {blob:await r.blob(),filename:m?.[1]||`review.${format}`};
}
export async function createApiKey(email:string,name:string){ const r=await fetch(`${API_BASE_URL}/api/v1/auth/api-keys`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({email,name})}); if(!r.ok)return errorOf(r); return r.json() as Promise<ApiKeyCreated>; }
export const listApiKeys=()=>request<ApiKeyInfo[]>('/api/v1/auth/api-keys');
export async function revokeApiKey(id:string){const r=await fetch(`${API_BASE_URL}/api/v1/auth/api-keys/${encodeURIComponent(id)}`,{method:'DELETE',headers:authHeaders()});if(!r.ok)return errorOf(r);}
export const orkgSearch=(q:string,size=20)=>request<OrkgSearchResult>(`/api/v1/orkg/search?q=${encodeURIComponent(q)}&size=${size}`);
export const askOrkg=(query:string,size=20,provider?:string)=>request<OrkgAskResult>('/api/v1/orkg/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,size,...(provider?{provider}:{})})});
export const orkgConnect=(username:string,password:string)=>request<OrkgConnectResult>('/api/v1/orkg/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
export const sparql=(query:string,limit?:number)=>request<SparqlResult>('/api/v1/orkg/sparql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,...(limit?{limit}:{})})});
