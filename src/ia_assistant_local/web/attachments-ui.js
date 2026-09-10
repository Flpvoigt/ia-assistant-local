/* Local attachment review. File contents never reach the model before confirmation. */
window.installAttachments = function({api, message, getAccount, addContexts, addImage, imageCount, onConverted}) {
  const byId = id => document.getElementById(id);
  const input = byId("attachmentInput");
  const folder = byId("attachmentFolder");
  const camera = byId("attachmentCamera");
  const trigger = byId("attachBtn");
  const menu = byId("attachmentMenu");
  let originals = [], busy = false, generation = 0;
  const urls = new Set();
  const blocked = /(^|\/)(\.env(?:\..*)?|\.git|\.venv|venv|node_modules|__pycache__|\.ssh|data)(\/|$)|\.(?:pem|key|p12|pfx|sqlite3?|db)$/i;
  const supported = /\.(pdf|docx|txt|md|csv|json|yaml|yml|xml|html|css|js|ts|py|java|c|cpp|h|sql|log|png|jpe?g|webp)$/i;
  const read = file => new Promise((resolve,reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Não foi possível ler " + file.name));
    reader.readAsDataURL(file);
  });
  function setMenu(open) {
    menu.hidden = !open;
    trigger.classList.toggle("is-open", open);
    trigger.setAttribute("aria-expanded", String(open));
  }
  function setBusy(value) {
    busy = value;
    trigger.classList.toggle("is-busy", value);
    trigger.setAttribute("aria-label", value ? "Preparando anexo" : "Adicionar ao chat");
  }
  function reportRejected(items) {
    if(items.length) message("system", "Não foi possível anexar " + items.length + " item(ns): " + items.slice(0,8).join("; "));
  }
  function attachPrepared(entries, rejected) {
    const texts = entries.filter(item => item.result.kind === "text");
    let images = entries.filter(item => item.result.kind === "image");
    if(images.length + imageCount() > 1) {
      const available = Math.max(0, 1 - imageCount());
      rejected.push(...images.slice(available).map(item => item.path + " (uma imagem por mensagem)"));
      images = images.slice(0, available);
    }
    if(texts.some(item => !item.content.trim() || item.content.length > 12000) ||
        texts.reduce((total,item) => total + item.content.length, 0) > 60000) {
      rejected.push("contexto de texto (limite de 12.000 caracteres por arquivo e 60.000 no total)");
      texts.length = 0;
    }
    const accepted = [...texts, ...images];
    if(originals.reduce((total,item) => total + item.file.size, 0) +
        accepted.reduce((total,item) => total + item.file.size, 0) > 20_000_000) {
      rejected.push("lote (os originais desta sessão atingiram 20 MB)");
      reportRejected(rejected); return;
    }
    try {
      if(texts.length) addContexts(texts.map(item => ({source:"Arquivo: " + item.path, content:item.content})));
      for(const item of images) addImage({name:item.path, dataUrl:item.dataUrl});
      originals.push(...accepted);
    } catch(error) { rejected.push(error.message); }
    reportRejected(rejected);
    byId("inputField").focus();
  }
  async function stage(files, token = generation) {
    if(!getAccount()) return;
    if(busy) return message("system", "Aguarde a leitura atual antes de adicionar outros anexos.");
    setMenu(false); setBusy(true);
    const entries = [], rejected = [];
    try {
      for(const {file,path} of files) {
        if(token !== generation) return;
        if(blocked.test(path) || !supported.test(path)) { rejected.push(path + " (formato não permitido ou arquivo privado)"); continue; }
        if(entries.some(item => item.path === path)) continue;
        if(entries.length >= 50 || file.size > 5_000_000 ||
            entries.reduce((sum,item)=>sum+item.file.size,0)+file.size > 20_000_000) {
          rejected.push(path + " (limite: 50 arquivos, 5 MB por arquivo, 20 MB no lote)"); continue;
        }
        try {
          const dataUrl = await read(file);
          if(file.size >= 750_000 && !file.type.startsWith("image/")) {
            const task = await api("/api/tasks", {method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify({kind:"extract",name:file.name,mime_type:file.type,data:dataUrl.split(",")[1]})});
            window.dispatchEvent(new CustomEvent("oraculo:task-created",{detail:task.task}));
            rejected.push(path + " (processando em segundo plano)");
            continue;
          }
          const result = await api("/api/attachments/extract", {method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({name:file.name,mime_type:file.type,data:dataUrl.split(",")[1]})});
          if(token !== generation) return;
          entries.push({file,path,dataUrl,result:result.attachment,content:result.attachment.content || ""});
        } catch(error) { rejected.push(path + ": " + error.message); }
      }
    } finally {
      if(token === generation) {
        attachPrepared(entries, rejected);
        setBusy(false);
      }
    }
  }
  function choose(files) {
    return stage([...files].map(file=>({file,path:file.webkitRelativePath || file.name})));
  }
  async function walk(entry, prefix, output) {
    if(output.length >= 200) throw new Error("Pasta grande demais. Selecione uma subpasta com até 200 arquivos.");
    const path = prefix + entry.name;
    if(blocked.test(path)) { output.push({file:null,path}); return; }
    if(entry.isFile) {
      const file = await new Promise((resolve,reject)=>entry.file(resolve,reject));
      output.push({file,path});
    } else if(entry.isDirectory) {
      const reader = entry.createReader();
      while(true) {
        const batch = await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));
        if(!batch.length) break;
        for(const child of batch) await walk(child,path+"/",output);
      }
    }
  }
  function saveDownload(data, name, token) {
    if(token !== generation) return;
    const bytes = Uint8Array.from(atob(data), c=>c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type:"application/pdf"})); urls.add(url);
    const bubble = message("assistant","PDF criado localmente. ");
    const link = document.createElement("a"); link.href = url; link.download = name;
    link.textContent = "Baixar " + name; bubble.append(link);
  }
  async function convert(item) {
    const token = generation;
    const response = await api("/api/attachments/pdf", {method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({name:item.file.name,mime_type:item.file.type,data:item.dataUrl.split(",")[1]})});
    saveDownload(response.data,item.file.name.replace(/\.[^.]+$/,"")+".pdf",token);
    if(token === generation) onConverted(item.path);
  }
  trigger.addEventListener("click", event => {
    event.stopPropagation();
    if(getAccount() && !busy) setMenu(menu.hidden);
  });
  byId("chooseAttachmentFiles").addEventListener("click",()=>{ setMenu(false); input.click(); });
  byId("chooseAttachmentFolder").addEventListener("click",()=>{ setMenu(false); folder.click(); });
  byId("chooseAttachmentCamera").addEventListener("click",()=>{ setMenu(false); camera.click(); });
  input.addEventListener("change",()=>{choose(input.files); input.value="";});
  folder.addEventListener("change",()=>{choose(folder.files); folder.value="";});
  camera.addEventListener("change",()=>{choose(camera.files); camera.value="";});
  document.addEventListener("click", event=>{ if(!menu.hidden && !menu.contains(event.target)) setMenu(false); });
  document.addEventListener("keydown", event=>{ if(event.key === "Escape") setMenu(false); });
  byId("inputForm").addEventListener("paste", event=>{
    if(!getAccount()) return;
    const items=[...(event.clipboardData?.items || [])].filter(item=>item.kind==="file" && item.type.startsWith("image/"));
    if(!items.length) return; // Ordinary text paste remains native.
    event.preventDefault();
    const files=items.map(item=>item.getAsFile()).filter(Boolean).map((file,index)=>{
      const extension={"image/png":"png","image/jpeg":"jpg","image/webp":"webp"}[file.type] || "unsupported";
      return new File([file],"imagem-colada-"+Date.now()+"-"+index+"."+extension,{type:file.type});
    });
    choose(files);
  });
  for(const name of ["dragenter","dragover"]) document.addEventListener(name,event=>{
    if(![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault();
    if(getAccount()) { document.body.classList.add("drop-active"); event.dataTransfer.dropEffect="copy"; }
  });
  document.addEventListener("dragleave",event=>{
    if(!event.relatedTarget) document.body.classList.remove("drop-active");
  });
  document.addEventListener("drop",async event=>{
    if(![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault(); document.body.classList.remove("drop-active");
    if(!getAccount()) return;
    const token=generation;
    // Capture entries synchronously: browsers clear the drag data store after this event.
    const roots=[...event.dataTransfer.items].map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
    const fallback=[...event.dataTransfer.files];
    try {
      const files=[];
      if(roots.length) for(const root of roots) await walk(root,"",files);
      else for(const file of fallback) files.push({file,path:file.name});
      if(token===generation) await stage(files,token);
    } catch(error) { message("system","Não foi possível ler a pasta: "+error.message); }
  });
  function reset() {
    generation++; setBusy(false); originals=[]; setMenu(false);
    for(const url of urls) URL.revokeObjectURL(url); urls.clear();
  }
  window.addEventListener("oraculo:account",reset);
  return {
    reset,
    forget(name) { originals=originals.filter(item=>item.path!==name); },
    async handle(text) {
      if(!(/^\/pdf\b/i.test(text) || (/\bpdf\b/i.test(text) && /\b(convert|transform|export|ger[ae])/i.test(text)))) return false;
      if(!originals.length) {
        message("system","Anexe e confirme o arquivo nesta sessão antes de pedir a conversão. Arquivos de chats antigos precisam ser anexados novamente.");
        return true;
      }
      let targets=originals.filter(item=>text.toLowerCase().includes(item.file.name.toLowerCase()));
      if(!targets.length && originals.length===1) targets=originals;
      if(!targets.length && /\b(todos|todas)\b/i.test(text)) targets=originals;
      if(!targets.length) {
        message("system","Qual arquivo deseja converter? Escreva /pdf nome-do-arquivo ou /pdf todos."); return true;
      }
      for(const item of targets) {
        try { await convert(item); } catch(error) { message("system",item.path+": "+error.message); }
      }
      return true;
    }
  };
};
