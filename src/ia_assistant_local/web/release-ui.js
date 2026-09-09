(() => {
  const button=document.getElementById("launchRelease");
  let user=null, timer=0, epoch=0, publishing=false;
  const dialog=document.createElement("dialog");dialog.className="release-dialog";
  dialog.setAttribute("aria-label","Lançamento do Oráculo");document.body.append(dialog);
  async function api(path,body){
    const response=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||"Não foi possível concluir.");
    return data;
  }
  const close=()=>{if(publishing)return;clearTimeout(timer);dialog.close();dialog.replaceChildren();};
  dialog.addEventListener("cancel",event=>{if(publishing)event.preventDefault();else clearTimeout(timer);});
  function launch(){
    if(user?.role!=="owner" || user.username!=="felipe")return;
    dialog.className="release-dialog";
    dialog.innerHTML='<header><h2>Lançar nova versão</h2><button type="button" class="release-close" aria-label="Fechar">×</button></header><p>Cria um commit e envia para a main do origin. Não atualiza automaticamente os computadores da equipe.</p><label>Novidades para o guia (uma por linha)<textarea id="releaseNotes" rows="6" maxlength="2880"></textarea></label><button type="button" class="btn" id="releasePrepare">Verificar lançamento</button><pre id="releasePreview"></pre><label class="profile-toggle" id="releaseConsent" hidden><input type="checkbox" id="releaseReviewed"> Revisei os arquivos no editor, as novidades e o destino. Autorizo o commit e o push.</label><button type="button" class="btn primary" id="releasePublish" hidden>Confirmar lançamento</button><p id="releaseStatus" role="status"></p>';
    dialog.querySelector(".release-close").onclick=close;
    const notes=dialog.querySelector("#releaseNotes"),status=dialog.querySelector("#releaseStatus");
    notes.value="Imagens por Ctrl+V, com miniaturas e envio sem texto\nArquivos e pastas com revisão e conversão local para PDF\nConfigurações de aparência por conta\nRaciocínio com ajuste gradual e efeito Full contínuo\nDiagnóstico local dos erros recebidos";
    let token=null;
    const consent=dialog.querySelector("#releaseConsent"),publish=dialog.querySelector("#releasePublish"),reviewed=dialog.querySelector("#releaseReviewed"),prepare=dialog.querySelector("#releasePrepare");
    notes.oninput=()=>{token=null;publish.hidden=true;consent.hidden=true;};
    prepare.onclick=async()=>{
      prepare.disabled=true;token=null;publish.hidden=true;consent.hidden=true;status.textContent="Verificando Git e arquivos…";
      try{
        const plan=await api("/api/admin/release/prepare",{notes:notes.value.split("\n").filter(line=>line.trim())});
        token=plan.token;dialog.querySelector("#releasePreview").textContent="Oráculo "+plan.version+"\nDestino: "+plan.remote+" · "+plan.branch+"\n\nArquivos:\n"+[...plan.files,"Manifesto de versão e guia"].join("\n");
        consent.hidden=false;reviewed.checked=false;publish.hidden=false;publish.disabled=true;
        status.textContent="Prévia válida por cinco minutos. A verificação automática não substitui a revisão de segredos no código.";
      }catch(error){status.textContent=error.message;}finally{prepare.disabled=false;}
    };
    reviewed.onchange=()=>publish.disabled=!reviewed.checked;
    publish.onclick=async()=>{
      if(!token || !reviewed.checked || publishing)return;
      publishing=true;publish.disabled=true;prepare.disabled=true;notes.disabled=true;reviewed.disabled=true;
      status.textContent="Criando commit e enviando… Não feche o servidor.";
      try{
        const result=await api("/api/admin/release/publish",{token,confirmed:true});
        status.textContent=result.message+" Versão "+result.version+". Commit "+result.commit.slice(0,8)+".";
      }catch(error){status.textContent=error.message+" Confira o estado do Git antes de tentar novamente.";}
      finally{publishing=false;token=null;publish.hidden=true;prepare.disabled=false;notes.disabled=false;}
    };
    dialog.showModal();
  }
  function welcome(release){
    const key="oraculo-release-seen-"+user.id;
    try{if(localStorage.getItem(key)===release.version)return;}catch{}
    dialog.className="release-dialog release-welcome";
    dialog.innerHTML='<button class="release-skip" type="button">Pular animação</button><div class="release-film"><div class="release-orbit"></div><div class="release-core"></div><p class="release-kicker">UMA NOVA EXPERIÊNCIA</p><h2 class="release-brand">ORÁCULO</h2><p class="release-version"></p><p class="release-caption">Mais clareza. Mais possibilidades.</p></div><section class="release-guide" hidden><p class="release-kicker">PRONTO PARA EXPLORAR</p><h2>Conheça as novidades</h2><ol></ol><p class="release-local">Este guia aparece uma vez por versão, nesta conta e navegador.</p><button type="button" class="btn primary" id="releaseDone">Começar</button></section>';
    dialog.querySelector(".release-version").textContent=release.version;
    for(const note of release.notes){
      const item=document.createElement("li");item.textContent=note;dialog.querySelector("ol").append(item);
    }
    const guide=()=>{clearTimeout(timer);dialog.querySelector(".release-film").hidden=true;dialog.querySelector(".release-skip").hidden=true;dialog.querySelector(".release-guide").hidden=false;dialog.querySelector("#releaseDone").focus();};
    dialog.querySelector(".release-skip").onclick=guide;
    dialog.querySelector("#releaseDone").onclick=()=>{try{localStorage.setItem(key,release.version);}catch{}close();};
    dialog.showModal();
    if(matchMedia("(prefers-reduced-motion: reduce)").matches || document.body.classList.contains("layout-still"))guide();
    else timer=setTimeout(guide,7000);
  }
  button.onclick=launch;
  window.addEventListener("oraculo:account",async event=>{
    const turn=++epoch;user=event.detail.user;
    button.hidden=!(user?.role==="owner" && user.username==="felipe");
    if(!publishing)close();
    if(!user || user.must_change_password)return;
    try{
      const release=await api("/api/release");
      if(turn===epoch && release.published && !dialog.open)welcome(release);
    }catch{/* Release notes are optional; login must still work. */}
  });
})();

