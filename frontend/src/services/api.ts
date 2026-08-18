import type { ApiKeyCreated, ApiKeyInfo, BackendModelsResponse, DocumentInfo, JobInfo, OrkgConnectResult, OrkgSearchResult, ReviewCreatePayload, ReviewOut, PreviewOut, SparqlResult } from '@/types';

export const API_BASE_URL=(import.meta.env.VITE_API_BASE_URL||'https://litreview-web.onrender.com').replace(/\/$/,'');
const KEY_STORAGE='research-gen.api-key';
export const getApiKey=()=>localStorage.getItem(KEY_STORAGE)||import.meta.env.VITE_API_KEY||'';
export const setApiKey=(key:string)=>localStorage.setItem(KEY_STORAGE,key.trim());
export const clearApiKey=()=>localStorage.removeItem(KEY_STORAGE);

// Silently provision an API key on first visit so the user never has to think about
// keys. Uploads and review generation need one; the picker (GET /models) is public.
export async function ensureApiKey():Promise<string>{
 const existing=getApiKey();
 if(existing)return existing;
 const email=`web-${crypto.randomUUID().slice(0,8)}@research-gen.app`;
 const created=await createApiKey(email,'web-ui');
 setApiKey(created.api_key);
 return created.api_key;
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
 const r=await fetch(`${API_BASE_URL}/api/v1/documents`,{method:'POST',headers:authHeaders(),body:f});
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
export const orkgConnect=(username:string,password:string)=>request<OrkgConnectResult>('/api/v1/orkg/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
export const sparql=(query:string,limit?:number)=>request<SparqlResult>('/api/v1/orkg/sparql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,...(limit?{limit}:{})})});
