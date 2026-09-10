(() => {
  const button=document.getElementById("launchRelease");
  let user=null, timer=0, epoch=0, publishing=false, latestRelease=null, releasePoll=0, stopCinema=()=>{};
  const dialog=document.createElement("dialog");dialog.className="release-dialog";
  dialog.setAttribute("aria-label","Lançamento do Oráculo");document.body.append(dialog);
  async function api(path,body){
    const response=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||"Não foi possível concluir.");
    return data;
  }
  const close=()=>{if(publishing)return;clearTimeout(timer);stopCinema();dialog.close();dialog.replaceChildren();};
  dialog.addEventListener("cancel",event=>{if(publishing)event.preventDefault();else clearTimeout(timer);});
  function launch(){
    if(user?.role!=="owner" || user.username!=="felipe")return;
    dialog.className="release-dialog";
    dialog.innerHTML='<header><h2>Lançar nova versão</h2><button type="button" class="release-close" aria-label="Fechar">×</button></header><p>Cria um commit e envia para a main do origin. Não atualiza automaticamente os computadores da equipe.</p><label>Novidades para o guia (uma por linha)<textarea id="releaseNotes" rows="6" maxlength="2880"></textarea></label><button type="button" class="btn" id="releasePrepare">Verificar lançamento</button><pre id="releasePreview"></pre><label class="profile-toggle" id="releaseConsent" hidden><input type="checkbox" id="releaseReviewed"> Revisei os arquivos no editor, as novidades e o destino. Autorizo o commit e o push.</label><button type="button" class="btn primary" id="releasePublish" hidden>Confirmar lançamento</button><p id="releaseStatus" role="status"></p>';
    dialog.querySelector(".release-close").onclick=close;
    const notes=dialog.querySelector("#releaseNotes"),status=dialog.querySelector("#releaseStatus");
    notes.value="Detector de contradições com escolha da memória correta\nCofre privado criptografado e separado do contexto da IA\nFila de documentos com progresso, cancelamento e revisão\nOCR local de imagens e captura pela câmera do celular\nWeb Clipper para páginas, seleções e capturas de tela\nNovo painel de configurações organizado por área\nCentral do dev-chefe com métricas, permissões e auditoria\nApresentação cinematográfica 3D com identidade do Oráculo\nGuia de novidades paginado, responsivo e sem scrollbar";
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
        latestRelease={version:result.version,published:true,notes:notes.value.split("\n").filter(line=>line.trim())};
        window.setTimeout(()=>{if(user&&latestRelease){dialog.close();dialog.replaceChildren();welcome(latestRelease,true);}},1200);
      }catch(error){status.textContent=error.message+" Confira o estado do Git antes de tentar novamente.";}
      finally{publishing=false;token=null;publish.hidden=true;prepare.disabled=false;notes.disabled=false;}
    };
    dialog.showModal();
  }
  function cinematic(canvas){
    const context=canvas.getContext("2d"),particles=[];
    let frame=0,start=performance.now(),width=0,height=0,scale=1;
    const resize=()=>{
      const rect=canvas.getBoundingClientRect();scale=Math.min(devicePixelRatio||1,2);
      width=rect.width;height=rect.height;canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
      context.setTransform(scale,0,0,scale,0,0);
    };
    resize();window.addEventListener("resize",resize);
    for(let index=0;index<180;index++)particles.push({
      x:(Math.random()-.5)*1100,y:(Math.random()-.5)*720,z:80+Math.random()*1000,
      size:.5+Math.random()*1.5,phase:Math.random()*Math.PI*2,index
    });
    const render=now=>{
      const elapsed=(now-start)/1000,cx=width/2,cy=height*.43;
      context.clearRect(0,0,width,height);
      const glow=context.createRadialGradient(cx,cy,0,cx,cy,Math.min(width,height)*.42);
      glow.addColorStop(0,"rgba(87,219,235,.08)");glow.addColorStop(1,"rgba(0,0,0,0)");
      context.fillStyle=glow;context.fillRect(0,0,width,height);
      const projected=[];
      particles.forEach((particle,index)=>{
        let screenX,screenY,depth;
        if(elapsed<2.35){
          particle.z-=5.5+particle.size*2;
          if(particle.z<35){particle.z=1050;particle.x=(Math.random()-.5)*1100;particle.y=(Math.random()-.5)*720;}
          depth=430/particle.z;screenX=cx+particle.x*depth;screenY=cy+particle.y*depth;
        }else{
          const outer=index>=118,angle=(index/(outer?62:118))*Math.PI*2;
          const targetX=Math.cos(angle)*(outer?225:148),targetY=Math.sin(angle)*(outer?108:52);
          const targetZ=Math.sin(angle*(outer?3:2))*(outer?105:68);
          const force=Math.min(.1,.025+(elapsed-2.35)*.014);
          particle.x+=(targetX-particle.x)*force;particle.y+=(targetY-particle.y)*force;particle.z+=(targetZ-particle.z)*force;
          const rotation=elapsed*.16*(outer?-1:1),rotatedX=particle.x*Math.cos(rotation)-particle.z*Math.sin(rotation);
          const rotatedZ=particle.x*Math.sin(rotation)+particle.z*Math.cos(rotation);
          depth=520/(620+rotatedZ);screenX=cx+rotatedX*depth;screenY=cy+particle.y*depth;
        }
        projected.push({x:screenX,y:screenY});
        const alpha=Math.min(.9,.18+depth*.44)*(Math.sin(now*.002+particle.phase)*.18+.82);
        const palette=index%9===0?"216,103,255":index%13===0?"255,54,181":"116,225,245";
        context.beginPath();context.fillStyle="rgba("+palette+","+alpha+")";
        context.shadowBlur=particle.size>1.4?9:0;context.shadowColor="rgba("+palette+",.55)";
        context.arc(screenX,screenY,Math.max(.45,particle.size*Math.min(2.2,depth)),0,Math.PI*2);context.fill();
      });
      context.shadowBlur=0;
      if(elapsed>3){
        context.strokeStyle="rgba(169,131,234,.085)";context.lineWidth=.7;
        for(let index=0;index<projected.length;index+=3){
          const a=projected[index],b=projected[(index+3)%projected.length];
          const distance=Math.hypot(a.x-b.x,a.y-b.y);
          if(distance<62){context.beginPath();context.moveTo(a.x,a.y);context.lineTo(b.x,b.y);context.stroke();}
        }
      }
      frame=requestAnimationFrame(render);
    };
    frame=requestAnimationFrame(render);
    return()=>{cancelAnimationFrame(frame);window.removeEventListener("resize",resize);};
  }
  function welcome(release,force=false){
    const key="oraculo-release-seen-"+user.id;
    try{if(!force&&localStorage.getItem(key)===release.version)return;}catch{}
    dialog.className="release-dialog release-welcome";
    dialog.innerHTML='<button class="release-skip" type="button">Pular apresentação</button><div class="release-film"><canvas class="release-canvas"></canvas><div class="release-grid"></div><div class="release-depth"><i class="depth-plane p1"></i><i class="depth-plane p2"></i><i class="depth-plane p3"></i><i class="depth-plane p4"></i></div><div class="release-beam beam-a"></div><div class="release-beam beam-b"></div><div class="release-noise"></div><div class="release-vignette"></div><div class="release-hud release-hud-left"><b>ORC // CORE</b><span>BOOT SEQUENCE 05</span><span>LOCAL INSTANCE</span></div><div class="release-hud release-hud-right"><b>ENCRYPTED</b><span>MEMORY ONLINE</span><span>LATENCY 004 MS</span></div><div class="release-sequence" aria-live="polite"><span>VALIDANDO INTEGRIDADE</span><span>RECONSTRUINDO NÚCLEO</span><span>SINCRONIZANDO MEMÓRIA</span><span>SISTEMA PRONTO</span></div><div class="release-sigil"><i class="sigil-ring one"></i><i class="sigil-ring two"></i><i class="sigil-ring three"></i><i class="sigil-orb"></i><i class="sigil-axis"></i><i class="sigil-core"></i></div><div class="release-mark"><p class="release-kicker">INTELIGÊNCIA LOCAL · NOVA GERAÇÃO</p><h2 class="release-brand">ORÁCULO</h2><p class="release-version"></p><p class="release-caption">O núcleo evoluiu.</p></div><div class="release-feature-stream"><span>MEMÓRIA</span><span>PRIVACIDADE</span><span>AUTOMAÇÃO</span><span>CONTEXTO</span></div><div class="release-timeline"><i></i><b></b></div></div><section class="release-guide" hidden><p class="release-kicker">NÚCLEO ATUALIZADO</p><h2>Uma nova versão do Oráculo está pronta.</h2><p class="release-guide-intro">Explore o que mudou antes de continuar.</p><ol></ol><p class="release-local">Esta apresentação aparece uma vez por versão, nesta conta e navegador.</p><button type="button" class="btn primary" id="releaseDone">Iniciar nova experiência</button></section>';
    dialog.querySelector(".release-version").textContent=release.version;
    const list=dialog.querySelector("ol"),done=dialog.querySelector("#releaseDone");
    const controls=document.createElement("div");controls.className="release-guide-controls";
    controls.innerHTML='<button type="button" class="btn" id="releaseGuidePrev">Anterior</button><span id="releaseGuidePage"></span><button type="button" class="btn primary" id="releaseGuideNext">Próximo</button>';
    dialog.querySelector(".release-local").before(controls);
    const previous=controls.querySelector("#releaseGuidePrev"),next=controls.querySelector("#releaseGuideNext");
    const pageLabel=controls.querySelector("#releaseGuidePage"),perPage=innerWidth<650?3:6;
    const total=Math.max(1,Math.ceil(release.notes.length/perPage));let page=0;
    const renderPage=()=>{
      list.replaceChildren();
      release.notes.slice(page*perPage,(page+1)*perPage).forEach((note,index)=>{
        const item=document.createElement("li"),number=document.createElement("small"),text=document.createElement("span");
        number.textContent=String(page*perPage+index+1).padStart(2,"0");text.textContent=note;
        item.append(number,text);list.append(item);
      });
      pageLabel.textContent=(page+1)+" / "+total;previous.hidden=page===0;next.hidden=page===total-1;done.hidden=page!==total-1;
    };
    previous.onclick=()=>{page--;renderPage();};next.onclick=()=>{page++;renderPage();};renderPage();
    const guide=()=>{clearTimeout(timer);stopCinema();dialog.querySelector(".release-film").classList.add("release-film-exit");setTimeout(()=>{dialog.querySelector(".release-film").hidden=true;dialog.querySelector(".release-skip").hidden=true;dialog.querySelector(".release-guide").hidden=false;(next.hidden?done:next).focus();},450);};
    dialog.querySelector(".release-skip").onclick=guide;
    dialog.querySelector("#releaseDone").onclick=()=>{try{localStorage.setItem(key,release.version);}catch{}close();};
    dialog.showModal();
    stopCinema=cinematic(dialog.querySelector(".release-canvas"));
    if(matchMedia("(prefers-reduced-motion: reduce)").matches || document.body.classList.contains("layout-still"))guide();
    else timer=setTimeout(guide,15500);
  }
  button.onclick=launch;
  window.addEventListener("oraculo:open-panel",event=>{
    if(event.detail==="replay-release"&&user&&latestRelease?.published){
      if(dialog.open)dialog.close();
      welcome(latestRelease,true);
    }
  });
  async function checkRelease(turn){
    if(!user||user.must_change_password)return;
    try{
      const release=await api("/api/release");latestRelease=release;
      if(turn===epoch&&release.published&&!dialog.open)welcome(release);
    }catch{/* Release notes are optional; login must still work. */}
  }
  window.addEventListener("oraculo:account",async event=>{
    const turn=++epoch;user=event.detail.user;
    clearInterval(releasePoll);releasePoll=0;
    button.hidden=!(user?.role==="owner" && user.username==="felipe");
    if(!publishing)close();
    if(!user || user.must_change_password)return;
    await checkRelease(turn);
    if(turn===epoch&&user)releasePoll=setInterval(()=>checkRelease(epoch),45000);
  });
  document.addEventListener("visibilitychange",()=>{
    if(!document.hidden&&user)checkRelease(epoch);
  });
})();
