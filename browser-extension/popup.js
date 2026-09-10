const status=document.getElementById("status");
const setStatus=text=>status.textContent=text;
async function activeTab(){
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!tab?.id)throw new Error("Nenhuma página ativa.");
  if(!/^https?:/.test(tab.url||""))throw new Error("Esta página protegida não permite captura.");
  return tab;
}
async function oraculoTab(){
  const tabs=await chrome.tabs.query({url:["http://127.0.0.1:8765/*","http://localhost:8765/*"]});
  if(tabs[0])return tabs[0];
  const tab=await chrome.tabs.create({url:"http://127.0.0.1:8765/",active:true});
  await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{chrome.tabs.onUpdated.removeListener(listener);reject(new Error("O Oráculo não respondeu."));},10000);
    function listener(id,info){if(id===tab.id&&info.status==="complete"){clearTimeout(timeout);chrome.tabs.onUpdated.removeListener(listener);resolve();}}
    chrome.tabs.onUpdated.addListener(listener);
  });
  return tab;
}
async function deliver(clip){
  const target=await oraculoTab();
  await chrome.scripting.executeScript({target:{tabId:target.id},func:value=>{
    window.postMessage({source:"oraculo-web-clipper",clip:value},location.origin);
  },args:[clip]});
  await chrome.tabs.update(target.id,{active:true});
}
async function capture(action){
  const tab=await activeTab();
  if(action==="image"){
    const dataUrl=await chrome.tabs.captureVisibleTab(tab.windowId,{format:"png"});
    return {kind:"image",title:tab.title||"Captura da página",url:tab.url,dataUrl};
  }
  const [{result}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:mode=>{
    const selection=String(getSelection()||"").trim();
    const content=mode==="selection"?selection:String(document.body?.innerText||"").trim();
    return {kind:"text",title:document.title,url:location.href,content:content.slice(0,40000)};
  },args:[action]});
  if(!result.content)throw new Error(action==="selection"?"Selecione um trecho primeiro.":"Nenhum texto visível encontrado.");
  return result;
}
document.addEventListener("click",async event=>{
  const action=event.target.dataset.action;if(!action)return;
  document.querySelectorAll("button").forEach(button=>button.disabled=true);setStatus("Preparando revisão…");
  try{await deliver(await capture(action));setStatus("Aberto no Oráculo para revisão.");setTimeout(()=>window.close(),500);}
  catch(error){setStatus(error.message);document.querySelectorAll("button").forEach(button=>button.disabled=false);}
});
