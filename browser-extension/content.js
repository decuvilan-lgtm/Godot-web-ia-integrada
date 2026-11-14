(() => {
"use strict";
const CHANNEL="GODOT_CONTROLLER_BRIDGE_V1", pending=new Map(); let sequence=0;
function injectPageBridge(){
 if(document.documentElement?.dataset.godotControllerBridge==="loaded") return;
 const script=document.createElement("script"); script.src=chrome.runtime.getURL("page-bridge.js"); script.async=false;
 script.onload=()=>script.remove(); (document.documentElement||document.head).appendChild(script);
 if(document.documentElement) document.documentElement.dataset.godotControllerBridge="loaded";
}
window.addEventListener("message",event=>{
 if(event.source!==window||event.origin!==location.origin) return;
 const data=event.data; if(!data||data.channel!==CHANNEL||data.direction!=="response") return;
 const resolve=pending.get(data.request_id); if(!resolve) return; pending.delete(data.request_id); resolve(data.result);
});
chrome.runtime.onMessage.addListener((message,_sender,sendResponse)=>{
 if(!message||message.channel!==CHANNEL||message.type!=="execute") return false;
 const requestId="ext-"+Date.now()+"-"+(++sequence);
 const timeout=setTimeout(()=>{pending.delete(requestId);sendResponse({ok:false,error:"BRIDGE_TIMEOUT",message:"The editor adapter did not respond."});},10000);
 pending.set(requestId,result=>{clearTimeout(timeout);sendResponse(result);});
 window.postMessage({channel:CHANNEL,direction:"request",request_id:requestId,command:message.command},location.origin);
 return true;
});
injectPageBridge(); window.addEventListener("DOMContentLoaded",injectPageBridge,{once:true});
chrome.runtime.sendMessage({channel:CHANNEL,type:"bridge-ready",href:location.href});
})();
