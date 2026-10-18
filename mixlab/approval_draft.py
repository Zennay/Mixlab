"""Explicit private working-draft export/restore for human playlist approval.

Never a rights or consent artifact: imported drafts restore fields only.
"""
DRAFT_JS = r"""
const DRAFT_KIND="mixlab-private-playlist-approval-draft-v1";
const safeDraftSeconds=raw=>
 typeof raw==="string"&&raw.length<=32&&
 (raw===""||(Number.isFinite(Number(raw))&&Number(raw)>=0&&Number(raw)<=900));
function draftSnapshot(){
 const beats=Number(el("beats").value);
 if(!Number.isInteger(beats)||beats<1||beats>64)
  throw Error("Set valid transition beats (1–64) before saving.");
 const declared=inputs.map(x=>({
  path:x.track.path,sha256:x.track.sha256,rights:x.select.value,
  provenance:x.provenance.value,first_downbeat:x.downbeat.value
 }));
 const transitions=pairs.map(x=>({
  a:x.a.value,b:x.b.value,family:x.family.value
 }));
 const data={schema_version:1,kind:DRAFT_KIND,plan_sha256:bundle.plan_sha256,
  source_sha256s:tracks.map(x=>x.sha256),beats,tracks:declared,pairs:transitions,
  private_only:true,approved:false,rights_consented:false};
 validateDraft(data);
 return data;
}
function keysExactly(value,expected){
 if(!value||typeof value!=="object"||Array.isArray(value))return false;
 const actual=Object.keys(value).sort();
 return actual.length===expected.length&&expected.slice().sort().every((key,i)=>actual[i]===key);
}
function validateDraft(data){
 const top=["schema_version","kind","plan_sha256","source_sha256s","beats",
  "tracks","pairs","private_only","approved","rights_consented"];
 if(!keysExactly(data,top)||data.schema_version!==1||
  data.kind!==DRAFT_KIND||data.plan_sha256!==bundle.plan_sha256||
  !Array.isArray(data.source_sha256s)||
  JSON.stringify(data.source_sha256s)!==JSON.stringify(tracks.map(t=>t.sha256))||
  !Number.isInteger(data.beats)||data.beats<1||data.beats>64||
  data.private_only!==true||data.approved!==false||
  data.rights_consented!==false||
  !Array.isArray(data.tracks)||data.tracks.length!==tracks.length||
  !Array.isArray(data.pairs)||data.pairs.length!==pairs.length)
  throw Error("Private working draft is not tied to this exact original set plan.");
 for(let i=0;i<data.tracks.length;i++){
  const row=data.tracks[i],source=tracks[i];
  if(!keysExactly(row,["path","sha256","rights","provenance","first_downbeat"])||
    row.path!==source.path||row.sha256!==source.sha256||
    typeof row.rights!=="string"||(!rights.includes(row.rights)&&row.rights!=="")||
    typeof row.provenance!=="string"||row.provenance.length>300||
    [...row.provenance].some(c=>c.charCodeAt(0)<32)||
    !safeDraftSeconds(row.first_downbeat))
   throw Error("Draft contains a changed source, malformed permission field or downbeat.");
 }
 for(const item of data.pairs){
  if(!keysExactly(item,["a","b","family"])||
    !safeDraftSeconds(item.a)||!safeDraftSeconds(item.b)||
    typeof item.family!=="string"||
    !["","baseline","bass_swap","echo_exit","hard_cut"].includes(item.family))
   throw Error("Draft contains invalid manual transition cue fields.");
 }
 return data;
}
el("draft-download").addEventListener("click",()=>{
 try{
  const draft=draftSnapshot();
  const json=JSON.stringify(draft,null,2)+"\n";
  if(json.length>65536)throw Error("Working draft exceeds private size limit.");
  const blob=new Blob([json],{type:"application/json"});
  const link=document.createElement("a"),url=URL.createObjectURL(blob);
  link.href=url;link.download="mixlab-playlist-working-draft.private.json";
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  el("draft-status").textContent="Private unapproved draft downloaded explicitly. "+
   "Rights consent and order approval are never carried into a draft.";
 }catch(error){el("draft-status").textContent=error.message||"Cannot save partial draft.";}
});
el("draft-open").addEventListener("change",async function(){
 const file=this.files&&this.files[0];if(!file)return;
 this.value="";
 if(file.size<2||file.size>65536||file.name.endsWith(".json")===false){
  el("draft-status").textContent="Choose an original private JSON draft <=64 KiB.";return;
 }
 try{
  const draft=validateDraft(JSON.parse(await file.text()));
  stopRehearsal("Restoring a human draft stopped playback.");
  for(const item of auditions)if(item?.player)item.player.pause();
  el("beats").value=String(draft.beats);
  draft.tracks.forEach((row,i)=>{
   inputs[i].select.value=row.rights;
   inputs[i].provenance.value=row.provenance;
   inputs[i].downbeat.value=row.first_downbeat;
  });
  draft.pairs.forEach((row,i)=>{
   pairs[i].a.value=row.a;pairs[i].b.value=row.b;
   pairs[i].family.value=row.family;
  });
  // Never restore consent/approval from any file or prior browser session.
  el("rights-ack").checked=false;el("order-ack").checked=false;
  el("draft-status").textContent="Manual fields restored from matching private draft. "+
   "Nothing approved: recheck rights, exact cues and both consent boxes.";
 }catch(error){el("draft-status").textContent=
  error.message||"Foreign or malformed private draft refused.";}
});
"""
