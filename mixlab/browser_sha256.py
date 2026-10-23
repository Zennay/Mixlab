"""Bounded browser-side SHA-256 for offline, private MixLab show pages.

No external CDN, browser storage, network, music upload, or WebCrypto
whole-file allocation. Hashes local File slices before playback is armed.
"""

SHA256_BROWSER_JS = r"""
const SHA_K = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
]);
const shaRotate=(v,n)=>(v>>>n)|(v<<(32-n));
function newStreamingSHA256(){
  const h=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                           0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
  const buffer=new Uint8Array(64);
  let used=0, bytes=0, finished=false;
  function block(){
    const w=new Uint32Array(64);
    for(let i=0;i<16;i++){const j=i*4;
      w[i]=((buffer[j]<<24)|(buffer[j+1]<<16)|(buffer[j+2]<<8)|buffer[j+3])>>>0;
    }
    for(let i=16;i<64;i++){
      const x=w[i-15],y=w[i-2];
      const s0=shaRotate(x,7)^shaRotate(x,18)^(x>>>3);
      const s1=shaRotate(y,17)^shaRotate(y,19)^(y>>>10);
      w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
    }
    let [a,b,c,d,e,f,g,t]=h;
    for(let i=0;i<64;i++){
      const s1=shaRotate(e,6)^shaRotate(e,11)^shaRotate(e,25);
      const ch=(e&f)^(~e&g);
      const add=(t+s1+ch+SHA_K[i]+w[i])>>>0;
      const s0=shaRotate(a,2)^shaRotate(a,13)^shaRotate(a,22);
      const maj=(a&b)^(a&c)^(b&c);
      const next=(s0+maj)>>>0;
      t=g;g=f;f=e;e=(d+add)>>>0;d=c;c=b;b=a;a=(add+next)>>>0;
    }
    const result=[a,b,c,d,e,f,g,t];
    for(let i=0;i<8;i++)h[i]=(h[i]+result[i])>>>0;
  }
  function feed(chunk,account=true){
    if(finished)throw Error("SHA already finalized");
    if(account)bytes+=chunk.length;
    for(let offset=0;offset<chunk.length;){
      const n=Math.min(64-used,chunk.length-offset);
      buffer.set(chunk.subarray(offset,offset+n),used);used+=n;offset+=n;
      if(used===64){block();used=0;}
    }
  }
  return {
    update:chunk=>feed(chunk),
    hex:()=>{
      if(finished)throw Error("SHA already finalized");
      const bits=bytes*8;
      feed(Uint8Array.of(0x80),false);
      while(used!==56)feed(Uint8Array.of(0),false);
      const length=new Uint8Array(8);
      const high=Math.floor(bits/4294967296),low=bits>>>0;
      for(let i=0;i<4;i++){
        length[i]=(high>>>(24-8*i))&255;
        length[i+4]=(low>>>(24-8*i))&255;
      }
      feed(length,false);finished=true;
      return Array.from(h,v=>v.toString(16).padStart(8,"0")).join("");
    }
  };
}
async function sha256LocalFile(file,progress){
  const sha=newStreamingSHA256();
  const sliceBytes=1024*1024;
  for(let offset=0;offset<file.size;offset+=sliceBytes){
    const chunk=await file.slice(offset,Math.min(file.size,offset+sliceBytes)).arrayBuffer();
    sha.update(new Uint8Array(chunk));
    progress(Math.min(100,Math.floor(100*(offset+chunk.byteLength)/file.size)));
  }
  return sha.hex();
}
"""
