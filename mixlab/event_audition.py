"""Optional, strictly offline local original-source audition for Event Brief Studio.

The local browser reads only files a DJ explicitly picks. Reuse MixLab's
streaming JS SHA-256 instead of trusting names or approximate durations.
"""
from .browser_sha256 import SHA256_BROWSER_JS

AUDITION_JS = SHA256_BROWSER_JS + r"""
const auditionFiles=new Map();
let auditionObjectURL=null, auditionPath=null, auditionEpoch=0;
const auditionAudio=el("audition-audio"),auditionStatus=el("audition-status");
function auditionMessage(message){auditionStatus.textContent=message;}
function stopAudition(){
 auditionAudio.pause();auditionAudio.removeAttribute("src");auditionAudio.load();
 if(auditionObjectURL){URL.revokeObjectURL(auditionObjectURL);auditionObjectURL=null;}
 auditionPath=null;
 el("now-auditioning").textContent="Nothing armed";
}
function auditionButtonFor(song){
 const b=node("button","","Listen");
 b.type="button";b.setAttribute("aria-label","Audition original "+song.path);
 b.addEventListener("click",()=>armAudition(song.path));
 return b;
}
function armAudition(path){
 const entry=auditionFiles.get(path);
 if(!entry){
  auditionMessage("No SHA-verified local original selected for "+path+
   ". Use 'Select original audio' before listening.");return;
 }
 stopAudition();
 auditionPath=path;
 auditionObjectURL=URL.createObjectURL(entry);
 auditionAudio.src=auditionObjectURL;auditionAudio.load();
 el("now-auditioning").textContent=path;
 auditionMessage("Exact original SHA-256 verified. Press Play yourself. "+
  "Audio has not been uploaded or analyzed.");
}
function renderAuditionLibrary(){
 const list=el("audition-list"),search=el("audition-search").value.toLocaleLowerCase();
 list.replaceChildren();
 for(const song of tracks){
  if(!song.path.toLocaleLowerCase().includes(search)&&
      !song.tags.some(tag=>tag.includes(search)))continue;
  const item=node("li","audition-item"),title=node("span","audition-name",song.path);
  const badge=node("span","dim",song.bpm+" manual BPM · "+
   song.energy+"/10 energy · "+(auditionFiles.has(song.path)?"SHA verified":"not attached"));
  const button=auditionButtonFor(song);
  item.append(title,badge,button);list.append(item);
 }
 if(!list.children.length)list.append(node("li","dim","No local tracks match that search."));
 const count=auditionFiles.size;
 el("audition-count").textContent=count+"/"+tracks.length+" original files SHA-verified";
}
async function verifySelectedAuditionFiles(input){
 const list=Array.from(input.files||[]);
 if(!list.length)return;
 if(list.length>40){
  auditionMessage("Choose up to 40 files at a time (only 20 declared tracks).");
  input.value="";return;
 }
 const epoch=++auditionEpoch;
 input.disabled=true;
 let admitted=0,unmatched=0;
 try{
  for(const [i,file] of list.entries()){
   if(epoch!==auditionEpoch)break;
   const leaf=file.name.toLocaleLowerCase();
   const candidates=tracks.filter(t=>
    t.path.split("/").at(-1).toLocaleLowerCase()===leaf);
   if(!candidates.length||file.size===0||file.size>512*1024*1024){
    unmatched++;continue;
   }
   try{
    auditionMessage("Checking original audio "+(i+1)+"/"+list.length+
     " · "+file.name+" (offline)");
    const digest=await sha256LocalFile(file,percent=>{
     auditionMessage("Verifying "+file.name+": "+percent+"% · no upload");
    });
    if(epoch!==auditionEpoch)break;
    const matches=candidates.filter(song=>song.sha256===digest);
    if(!matches.length){unmatched++;continue;}
    for(const song of matches){
     // A file with identical full source SHA has identical source bytes.
     if(auditionPath===song.path)stopAudition();
     auditionFiles.set(song.path,file);admitted++;
    }
   }catch(_e){unmatched++;}
   renderAuditionLibrary();
  }
  auditionMessage("Local source import finished: "+admitted+
   " original track match(es); "+unmatched+
   " rejected/unmatched selection(s). No audio ever uploaded.");
 }finally{input.disabled=false;input.value="";renderAuditionLibrary();}
}
el("audition-file").addEventListener("change",function(){
 verifySelectedAuditionFiles(this);
});
el("audition-search").addEventListener("input",renderAuditionLibrary);
el("audition-stop").addEventListener("click",()=>{
 stopAudition();auditionMessage("Local preview stopped and detached.");
});
el("audition-intro").addEventListener("click",()=>{
 if(!auditionObjectURL){auditionMessage("Arm a verified original first.");return;}
 auditionAudio.currentTime=0;
 auditionMessage("At original intro (0:00). Press Play manually.");
});
el("audition-outro").addEventListener("click",()=>{
 if(!auditionObjectURL||!Number.isFinite(auditionAudio.duration)){
  auditionMessage("Arm and load a supported original source first.");return;
 }
 auditionAudio.currentTime=Math.max(0,auditionAudio.duration-30);
 auditionMessage("At final 30s of original. Press Play manually.");
});
auditionAudio.addEventListener("error",()=>{
 auditionMessage("Browser cannot decode this original format. Try a trusted local audio app; "+
  "MixLab has not modified or uploaded the file.");
});
window.addEventListener("pagehide",stopAudition);
renderAuditionLibrary();
"""
