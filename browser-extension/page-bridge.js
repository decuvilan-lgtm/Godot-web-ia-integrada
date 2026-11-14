(() => {
"use strict";
const CHANNEL="GODOT_CONTROLLER_BRIDGE_V1";
const ALLOWED=new Set(["editor.get_state","editor.list_capabilities","scene.open","scene.select_node","node.get_inspector","editor.open_panel"]);
window.addEventListener("message",async event=>{
 if(event.source!==window||event.origin!==location.origin) return;
 const data=event.data; if(!data||data.channel!==CHANNEL||data.direction!=="request") return;
 let result;
 try{
  const command=data.command;
  if(!command||typeof command!=="object"||!ALLOWED.has(command.action)) throw Object.assign(new Error("Command is not in the semantic allowlist."),{code:"COMMAND_NOT_ALLOWED"});
  const adapter=window.__godotEditorAgent;
  if(!adapter||typeof adapter.execute!=="function") throw Object.assign(new Error("This Godot Web build does not expose the semantic editor adapter yet."),{code:"GODOT_ADAPTER_UNAVAILABLE"});
  result=await adapter.execute(command);
  if(!result||typeof result!=="object") throw Object.assign(new Error("The editor adapter returned an invalid result."),{code:"INVALID_ADAPTER_RESULT"});
 }catch(error){result={ok:false,error:error.code||"ADAPTER_ERROR",message:String(error.message||error).slice(0,500)};}
 window.postMessage({channel:CHANNEL,direction:"response",request_id:data.request_id,result},location.origin);
});
})();
