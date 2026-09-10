(() => {
  const bridge=()=>window.OraculoBridge;
  const state={user:null,tasks:[],seen:new Set(),timer:0};
  const api=async(path,options={})=>{
    const response=await fetch(path,options);
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||"Não foi possível concluir.");
    return data;
  };
  const json=value=>({method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)});
  const dialog=document.createElement("dialog");dialog.className="feature-dialog";document.body.append(dialog);
  const escape=value=>String(value).replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  function shell(title,content){
    dialog.innerHTML='<header><div><small>ORÁCULO · LOCAL</small><h2>'+escape(title)+'</h2></div><button type="button" class="feature-close" aria-label="Fechar">×</button></header><div class="feature-content">'+content+'</div>';
    dialog.querySelector(".feature-close").onclick=()=>dialog.close();
    if(!dialog.open)dialog.showModal();
  }
  dialog.addEventListener("close",()=>{
    dialog.querySelectorAll("textarea,input").forEach(field=>field.value="");
    dialog.replaceChildren();
  });
  dialog.addEventListener("click",event=>{if(event.target===dialog)dialog.close();});

  async function openVault(){
    shell("Cofre privado",'<div class="feature-notice">Criptografia AES-GCM. A senha não é armazenada e o conteúdo nunca entra automaticamente no contexto da IA.</div><form id="vaultForm" class="feature-form"><label>Nome do item<input name="label" maxlength="120" required placeholder="Ex.: credencial do laboratório"></label><label>Informação protegida<textarea name="content" maxlength="20000" required rows="4"></textarea></label><label>Senha exclusiva do cofre<input name="password" type="password" minlength="10" autocomplete="new-password" required></label><label>Confirme a senha<input name="confirmation" type="password" minlength="10" autocomplete="new-password" required></label><button class="btn primary">Criptografar e guardar</button><p role="status"></p></form><div id="vaultList" class="feature-list"></div>');
    const list=dialog.querySelector("#vaultList"),form=dialog.querySelector("#vaultForm");
    async function load(){
      const data=await api("/api/vault");list.replaceChildren();
      if(!data.items.length){list.textContent="Nenhum item protegido.";return;}
      data.items.forEach(item=>{
        const card=document.createElement("article");card.className="feature-card";
        card.innerHTML='<strong>'+escape(item.label)+'</strong><small>'+new Date(item.updated_at*1000).toLocaleString("pt-BR")+'</small><div class="vault-actions"><input type="password" minlength="10" placeholder="Senha para desbloquear" aria-label="Senha do cofre"><button class="btn">Desbloquear</button><button class="btn danger">Excluir</button></div><textarea class="vault-reveal" readonly hidden></textarea>';
        const [unlock,remove]=card.querySelectorAll("button"),pass=card.querySelector("input"),reveal=card.querySelector("textarea");
        unlock.onclick=async()=>{try{const data=await api("/api/vault/"+item.id+"/unlock",json({passphrase:pass.value}));reveal.value=data.content;reveal.hidden=false;pass.value="";setTimeout(()=>{reveal.value="";reveal.hidden=true;},60000);}catch(error){bridge()?.message(error.message);}};
        remove.onclick=async()=>{if(confirm("Excluir este item do cofre permanentemente?")){await api("/api/vault/"+item.id,{method:"DELETE"});load();}};
        list.append(card);
      });
    }
    form.onsubmit=async event=>{
      event.preventDefault();const fields=new FormData(form),status=form.querySelector("[role=status]");
      if(fields.get("password")!==fields.get("confirmation")){status.textContent="As senhas do cofre não coincidem.";return;}
      status.textContent="Criptografando localmente…";
      try{await api("/api/vault",json({label:fields.get("label"),content:fields.get("content"),passphrase:fields.get("password")}));form.reset();status.textContent="Item protegido.";await load();}catch(error){status.textContent=error.message;}
    };
    await load();
  }

  const statusLabel={queued:"Na fila",running:"Processando",completed:"Concluída",failed:"Falhou",cancelled:"Cancelada"};
  async function useTask(task){
    const data=await api("/api/tasks/"+task.id),result=data.task.result;
    if(!result)return;
    const content=String(result.content||"");
    if(!content)throw new Error("A tarefa não produziu texto para revisar.");
    shell("Revisar resultado",'<div class="feature-notice">Nada será enviado à IA até você confirmar.</div><label class="feature-form">Trecho revisado<textarea id="taskReview" rows="14" maxlength="12000">'+escape(content.slice(0,12000))+'</textarea></label><div class="feature-actions"><button class="btn" id="taskBack">Voltar</button><button class="btn primary" id="taskUse">Anexar ao próximo envio</button></div>');
    dialog.querySelector("#taskBack").onclick=openTasks;
    dialog.querySelector("#taskUse").onclick=()=>{
      bridge().addContexts([{source:(task.kind==="ocr"?"OCR: ":"Tarefa: ")+task.label,content:dialog.querySelector("#taskReview").value}]);
      state.seen.add(task.id);dialog.close();bridge().message("Resultado revisado e anexado ao próximo envio.");
    };
  }
  async function refreshTasks(render=true){
    if(!state.user)return;
    try{const data=await api("/api/tasks");state.tasks=data.tasks;if(render&&dialog.open&&dialog.querySelector("#taskList"))renderTasks(data);}
    catch{clearTimeout(state.timer);state.timer=0;}
  }
  function startTaskPolling(){
    clearTimeout(state.timer);
    const tick=async()=>{
      await refreshTasks(true);
      state.timer=state.tasks.some(task=>["queued","running"].includes(task.status))
        ? setTimeout(tick,1500):0;
    };
    tick();
  }
  function renderTasks(data){
    const list=dialog.querySelector("#taskList");if(!list)return;list.replaceChildren();
    const availability=dialog.querySelector("#ocrAvailability");
    availability.textContent=data.ocr_available?"OCR local disponível.":"OCR requer Tesseract instalado; câmera e envio de imagens continuam disponíveis.";
    if(!data.tasks.length){list.textContent="Nenhuma tarefa nesta sessão.";return;}
    data.tasks.forEach(task=>{
      const card=document.createElement("article");card.className="feature-card";
      const title=document.createElement("strong");title.textContent=task.label;
      const meta=document.createElement("small");meta.textContent=(statusLabel[task.status]||task.status)+" · "+task.progress+"%";
      const bar=document.createElement("div");bar.className="task-progress";bar.innerHTML='<i style="width:'+Math.max(0,Math.min(100,task.progress))+'%"></i>';
      card.append(title,meta,bar);
      if(task.error){const error=document.createElement("p");error.className="task-error";error.textContent=task.error;card.append(error);}
      if(task.status==="completed"){
        const review=document.createElement("button");review.className="btn";review.textContent=state.seen.has(task.id)?"Revisar novamente":"Revisar resultado";review.onclick=()=>useTask(task).catch(error=>bridge()?.message(error.message));card.append(review);
      }else if(["queued","running"].includes(task.status)){
        const cancel=document.createElement("button");cancel.className="btn danger";cancel.textContent="Cancelar";cancel.onclick=async()=>{await api("/api/tasks/"+task.id,{method:"DELETE"});refreshTasks();};card.append(cancel);
      }
      list.append(card);
    });
  }
  async function openTasks(){
    shell("Tarefas em segundo plano",'<div id="ocrAvailability" class="feature-notice"></div><div id="taskList" class="feature-list"></div>');
    const data=await api("/api/tasks");state.tasks=data.tasks;renderTasks(data);
    if(data.tasks.some(task=>["queued","running"].includes(task.status)))startTaskPolling();
  }
  async function createOcr(item){
    try{
      const comma=String(item.dataUrl||"").indexOf(",");
      const mime=(String(item.dataUrl).match(/^data:([^;]+);base64,/)||[])[1]||"image/png";
      if(comma<0)throw new Error("Imagem inválida.");
      const data=await api("/api/tasks",json({kind:"ocr",name:item.name,mime_type:mime,data:item.dataUrl.slice(comma+1)}));
      bridge()?.message("OCR iniciado em segundo plano. Você pode continuar conversando.");
      await refreshTasks(false);startTaskPolling();return data.task;
    }catch(error){bridge()?.message(error.message);}
  }

  function reviewClip(clip){
    if(!state.user)return;
    const kind=clip?.kind,source=String(clip?.title||"Página da web").slice(0,120);
    if(kind==="image"&&/^data:image\/(png|jpeg|webp);base64,/i.test(String(clip.dataUrl||""))){
      shell("Revisar captura do Web Clipper",'<div class="feature-notice">Confira a imagem antes de anexá-la ao chat.</div><img class="clip-preview" src="'+escape(clip.dataUrl)+'" alt="Captura da página"><div class="feature-actions"><button class="btn" id="clipCancel">Cancelar</button><button class="btn primary" id="clipConfirm">Anexar captura</button></div>');
      dialog.querySelector("#clipCancel").onclick=()=>dialog.close();
      dialog.querySelector("#clipConfirm").onclick=()=>{try{bridge().addImage({name:source+".png",dataUrl:clip.dataUrl});dialog.close();}catch(error){bridge().message(error.message);}};
      return;
    }
    const content=String(clip?.content||"").slice(0,12000);
    if(!content.trim())return bridge()?.message("O Web Clipper não encontrou conteúdo para revisar.");
    shell("Revisar recorte da web",'<div class="feature-notice">Edite o trecho. Ele só será anexado depois da confirmação.</div><label class="feature-form">Conteúdo<textarea id="clipText" rows="14" maxlength="12000">'+escape(content)+'</textarea></label><div class="feature-actions"><button class="btn" id="clipCancel">Cancelar</button><button class="btn primary" id="clipConfirm">Anexar ao chat</button></div>');
    dialog.querySelector("#clipCancel").onclick=()=>dialog.close();
    dialog.querySelector("#clipConfirm").onclick=()=>{bridge().addContexts([{source:"Web: "+source,content:dialog.querySelector("#clipText").value}]);dialog.close();};
  }

  window.addEventListener("oraculo:open-panel",event=>{
    if(event.detail==="vault")openVault().catch(error=>bridge()?.message(error.message));
    if(event.detail==="tasks")openTasks().catch(error=>bridge()?.message(error.message));
  });
  window.addEventListener("oraculo:ocr-image",event=>createOcr(event.detail));
  window.addEventListener("oraculo:task-created",event=>{state.tasks.unshift(event.detail);startTaskPolling();bridge()?.message("Documento enviado para a fila. Abra Tarefas para acompanhar.");});
  window.addEventListener("message",event=>{
    if(event.source!==window||event.origin!==location.origin||event.data?.source!=="oraculo-web-clipper")return;
    reviewClip(event.data.clip);
  });
  window.addEventListener("oraculo:account",event=>{
    state.user=event.detail.user;state.tasks=[];state.seen.clear();
    clearTimeout(state.timer);state.timer=0;
    if(dialog.open)dialog.close();
  });
})();
