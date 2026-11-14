(() => {
"use strict";
const CHANNEL="GODOT_CONTROLLER_BRIDGE_V1", pending=new Map();
function injectPageBridge(){
 if(document.documentElement?.dataset.godotControllerBridge==="loaded") return;
 const script=document.createElement("script"); script.src=chrome.runtime.getURL("page-bridge.js"); script.async=false;
 script.onload=()=>script.remove(); (document.documentElement||document.head).appendChild(script);
 if(document.documentElement) document.documentElement.dataset.godotControllerBridge="loaded";
}
window.addEventListener("message",event=>{
 if(event.source!==window||event.origin!==location.origin) return;
 const data=event.data; if(!data||data.channel!==CHANNEL) return;
 if(data.direction==="host-command"){
  if(typeof data.request_id!=="string"||data.request_id.length>100||pending.has(data.request_id)) return;
  const timeout=setTimeout(()=>{
   pending.delete(data.request_id);
   window.postMessage({channel:CHANNEL,direction:"host-response",request_id:data.request_id,result:{ok:false,error:"BRIDGE_TIMEOUT",message:"The editor adapter did not respond."}},location.origin);
  },10000);
  pending.set(data.request_id,{timeout});
  window.postMessage({channel:CHANNEL,direction:"request",request_id:data.request_id,command:data.command},location.origin);
  return;
 }
 if(data.direction==="response"){
  const item=pending.get(data.request_id); if(!item) return;
  clearTimeout(item.timeout); pending.delete(data.request_id);
  window.postMessage({channel:CHANNEL,direction:"host-response",request_id:data.request_id,result:data.result},location.origin);
 }
});
injectPageBridge(); window.addEventListener("DOMContentLoaded",injectPageBridge,{once:true});
})();
