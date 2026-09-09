/* Local attachment review. File contents never reach the model before confirmation. */
window.installAttachments = function({api, message, getAccount, addContexts, addImage, imageCount, onConverted}) {
  const byId = id => document.getElementById(id);
  const overlay = byId("attachmentOverlay");
  const input = byId("attachmentInput");
  const folder = byId("attachmentFolder");
  const preview = byId("attachmentTextPreview");
  const image = byId("attachmentImagePreview");
  const meta = byId("attachmentMeta");
  const list = byId("attachmentList");
  let entries = [], originals = [], selected = -1, busy = false, generation = 0;
  const urls = new Set();
  const blocked = /(^|\/)(\.env(?:\..*)?|\.git|\.venv|venv|node_modules|__pycache__|\.ssh|data)(\/|$)|\.(?:pem|key|p12|pfx|sqlite3?|db)$/i;
  const supported = /\.(pdf|docx|txt|md|csv|json|yaml|yml|xml|html|css|js|ts|py|java|c|cpp|h|sql|log|png|jpe?g|webp)$/i;
  const read = file => new Promise((resolve,reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Não foi possível ler " + file.name));
    reader.readAsDataURL(file);
  });
  function persistPreview() {
    if(entries[selected]?.result.kind === "text") entries[selected].content = preview.value;
  }
  function select(index) {
    persistPreview(); selected = index;
    const item = entries[index];
    if(!item) { preview.value = ""; preview.hidden = true; image.hidden = true; return; }
    const isImage = item.result.kind === "image";
    preview.hidden = isImage; image.hidden = !isImage;
    if(isImage) image.src = item.dataUrl;
    else { image.removeAttribute("src"); preview.value = item.content; }
    meta.textContent = item.path + " · " + Math.ceil(item.file.size/1024) + " KB" +
      (item.result.truncated ? " · texto limitado a 12.000 caracteres; PDF usa o original" : "");
  }
  function render() {
    list.replaceChildren();
    entries.forEach((item,index) => {
      const row = document.createElement("label"); row.className = "attachment-row";
      const check = document.createElement("input"); check.type = "checkbox"; check.checked = item.checked;
      check.addEventListener("change", () => item.checked = check.checked);
      const button = document.createElement("button"); button.type = "button"; button.className = "btn";
      button.textContent = item.path; button.title = "Revisar " + item.path;
      button.addEventListener("click", event => { event.preventDefault(); select(index); });
      row.append(check,button); list.append(row);
    });
    byId("confirmAttachment").disabled = busy || !entries.length;
  }
  async function stage(files, token = generation) {
    if(!getAccount()) return;
    if(busy) return message("system", "Aguarde a leitura atual antes de adicionar outros anexos.");
    busy = true; overlay.classList.add("show"); render();
    const rejected = [];
    try {
      for(const {file,path} of files) {
        if(token !== generation) return;
        if(blocked.test(path) || !supported.test(path)) { rejected.push(path + " (formato não permitido ou arquivo privado)"); continue; }
        if(entries.some(item => item.path === path)) continue;
        if(entries.length >= 50 || file.size > 5_000_000 ||
            entries.reduce((sum,item)=>sum+item.file.size,0)+file.size > 20_000_000) {
          rejected.push(path + " (limite: 50 arquivos, 5 MB por arquivo, 20 MB no lote)"); continue;
        }
        meta.textContent = "Lendo " + path + "…";
        try {
          const dataUrl = await read(file);
          const result = await api("/api/attachments/extract", {method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({name:file.name,mime_type:file.type,data:dataUrl.split(",")[1]})});
          if(token !== generation) return;
          entries.push({file,path,dataUrl,result:result.attachment,content:result.attachment.content || "",checked:true});
        } catch(error) { rejected.push(path + ": " + error.message); }
      }
    } finally {
      if(token === generation) {
        busy = false; render(); select(entries.length ? 0 : -1);
        byId("attachmentNotice").textContent = rejected.length ?
          "Não incluídos (" + rejected.length + "): " + rejected.slice(0,12).join("; ") : "";
        if(!entries.length) meta.textContent = "Escolha arquivos ou uma pasta. Arquivos privados e formatos não suportados não serão incluídos.";
        if(!rejected.length && entries.length === 1 && entries[0].result.kind === "image" && !imageCount())
          byId("confirmAttachment").click();
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
  byId("attachBtn").addEventListener("click", () => {
    if(!getAccount()) return;
    overlay.classList.add("show");
    if(!entries.length) { meta.textContent = "Escolha arquivos ou uma pasta para revisar."; select(-1); render(); }
  });
  byId("chooseAttachmentFiles").addEventListener("click",()=>input.click());
  byId("chooseAttachmentFolder").addEventListener("click",()=>folder.click());
  input.addEventListener("change",()=>{choose(input.files); input.value="";});
  folder.addEventListener("change",()=>{choose(folder.files); folder.value="";});
  byId("cancelAttachment").addEventListener("click",()=>{
    generation++; busy=false; entries=[]; selected=-1; overlay.classList.remove("show");
    preview.value=""; image.removeAttribute("src"); render();
  });
  byId("confirmAttachment").addEventListener("click",()=>{
    if(busy) return;
    persistPreview();
    const accepted=entries.filter(item=>item.checked);
    if(!accepted.length) return;
    const texts=accepted.filter(item=>item.result.kind==="text");
    const images=accepted.filter(item=>item.result.kind==="image");
    if(images.length + imageCount() > 1) {
      byId("attachmentNotice").textContent = "Uma imagem por mensagem. Remova a imagem já preparada antes de adicionar outra.";
      return;
    }
    if(texts.some(item=>!item.content.trim() || item.content.length>12000) ||
        texts.reduce((n,item)=>n+item.content.length,0)>60000)
      return message("system","O contexto aceita até 60.000 caracteres no total e 12.000 por arquivo. Reduza os trechos ou desmarque arquivos; nada foi descartado.");
    if(originals.reduce((n,item)=>n+item.file.size,0) + accepted.reduce((n,item)=>n+item.file.size,0)>20_000_000)
      return message("system","Os originais desta sessão atingiram 20 MB. Inicie outro chat para adicionar mais.");
    try { addContexts(texts.map(item=>({source:"Arquivo: "+item.path,content:item.content}))); }
    catch(error) { return message("system",error.message); }
    for(const item of images) addImage({name:item.path,dataUrl:item.dataUrl});
    originals.push(...accepted);
    entries=[]; selected=-1; overlay.classList.remove("show"); render();
    byId("inputField").focus();
  });
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
    generation++; busy=false; entries=[]; originals=[]; selected=-1;
    for(const url of urls) URL.revokeObjectURL(url); urls.clear();
    overlay.classList.remove("show"); preview.value=""; image.removeAttribute("src"); render();
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
