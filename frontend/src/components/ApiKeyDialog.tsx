import {KeyRound, X, Copy, Check, Trash2, RefreshCw} from 'lucide-react';
import {useEffect,useState} from 'react';
import {createApiKey,getApiKey,listApiKeys,revokeApiKey,setApiKey} from '@/services/api';
import type {ApiKeyInfo} from '@/types';

export function ApiKeyDialog({onClose,onChanged}:{onClose:()=>void;onChanged:()=>void}){
 const [email,setEmail]=useState(''); const [name,setName]=useState('Research_Gen frontend');
 const [keys,setKeys]=useState<ApiKeyInfo[]>([]); const [busy,setBusy]=useState(false); const [created,setCreated]=useState(''); const [copied,setCopied]=useState(false); const [error,setError]=useState('');
 async function refresh(){if(!getApiKey())return;try{setKeys(await listApiKeys())}catch{}}
 useEffect(()=>{void refresh()},[]);
 async function create(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await createApiKey(email,name);setApiKey(r.api_key);setCreated(r.api_key);onChanged();await refresh()}catch(e){setError(e instanceof Error?e.message:'Impossible de créer la clé.')}finally{setBusy(false)}}
 async function revoke(id:string){if(!confirm('Révoquer cette clé API ?'))return;try{await revokeApiKey(id);if(id===keys.find(k=>k.prefix===getApiKey().slice(0,12))?.id)setCreated('');await refresh()}catch(e){setError(e instanceof Error?e.message:'Révocation impossible.')}}
 async function copy(){await navigator.clipboard.writeText(created);setCopied(true);setTimeout(()=>setCopied(false),1200)}
 return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur">
  <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl">
   <div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-2"><KeyRound className="text-emerald-400" size={18}/><div><h2 className="font-semibold">Clé API Research_Gen</h2><p className="text-xs text-slate-400">Authentification via X-API-Key.</p></div></div><button onClick={onClose}><X size={18}/></button></div>
   <form onSubmit={create} className="grid gap-2.5">
    <label className="text-xs text-slate-400">Email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} className="field"/></label>
    <label className="text-xs text-slate-400">Nom de la clé<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)} className="field"/></label>
    <button disabled={busy} className="primary">{busy?'Création…':'Créer une nouvelle clé'}</button>
   </form>
   {created&&<div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3"><p className="text-xs text-emerald-300">Clé créée et utilisée par ce navigateur. Elle n’est affichée en clair qu’à sa création.</p><div className="mt-2 flex gap-2"><code className="min-w-0 flex-1 break-all rounded bg-slate-950 p-2 text-xs">{created}</code><button onClick={copy} className="iconbtn" title="Copier">{copied?<Check size={15}/>:<Copy size={15}/>}</button></div></div>}
   {error&&<p className="mt-3 error">{error}</p>}
   <div className="mt-5 border-t border-slate-800 pt-3"><div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-medium">Clés associées</h3><button onClick={()=>void refresh()} className="iconbtn"><RefreshCw size={14}/></button></div>
    {!getApiKey()?<p className="text-xs text-slate-500">Créez une clé pour gérer les clés associées à votre utilisateur.</p>:keys.map(k=><div key={k.id} className="flex items-center justify-between gap-3 border-b border-slate-800 py-2 text-xs"><div><div>{k.name}</div><div className="text-slate-500">{k.prefix} · {k.revoked_at?'révoquée':'active'}</div></div>{!k.revoked_at&&<button onClick={()=>void revoke(k.id)} className="text-red-300 hover:text-red-200" title="Révoquer"><Trash2 size={15}/></button>}</div>)}
   </div>
  </div>
 </div>
}
