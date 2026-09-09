(() => {
  "use strict";
  const trigger=document.getElementById("profileTrigger");
  const accountBar=trigger.closest(".sidebar-account");
  const sidebar=document.getElementById("chatSidebar");
  trigger.setAttribute("aria-label","Abrir perfil");
  let account=null,permissions={},lastFocus=null;
  const defaults={text:"16",width:"1000",compact:false,quiet:false,effects:true};
  let layout={...defaults};
  function applyLayout(){
    document.body.style.setProperty("--chat-text-size",layout.text+"px");
    document.body.style.setProperty("--chat-content-width",layout.width+"px");
    document.body.classList.toggle("layout-compact",layout.compact);
    document.body.classList.toggle("layout-quiet",layout.quiet);
    document.body.classList.toggle("layout-still",!layout.effects);
  }
  function loadLayout(){
    layout={...defaults};
    try{
      const stored=JSON.parse(localStorage.getItem("oraculo-layout-"+account?.id)||"{}");
      for(const key of ["compact","quiet","effects"]) if(typeof stored[key]==="boolean") layout[key]=stored[key];
      if(["14","16","18","20"].includes(stored.text))layout.text=stored.text;
      if(["760","1000","1400"].includes(stored.width))layout.width=stored.width;
    }catch{}
    applyLayout();
  }
  const icon=paths=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+paths+'</svg>';
  const menu=document.createElement("div");
  menu.id="profileMenu";menu.className="profile-menu";menu.hidden=true;menu.setAttribute("role","menu");menu.setAttribute("aria-label","Menu da conta");
  const icons={
    admin:icon('<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>'),
    usage:icon('<path d="M4 16a9 9 0 1 1 16 0"/><path d="m12 12 5-4"/><circle cx="12" cy="12" r="1.5"/>'),
    mascot:icon('<rect x="5" y="6" width="14" height="15" rx="6"/><path d="M12 6V3M9 12v2m6-2v2"/>'),
    invite:icon('<path d="m3 11 18-8-7 18-3-8-8-2Zm8 2L21 3"/>'),
    settings:icon('<path d="m9 3-.6 3-2.5 1L3 6l-1 4 2.5 2L4 15l-1 2 3 3 3-1 3 1 2 1 3-3-1-3 2-2 3-1-1-4-3-.5L15 4l-2-1Z"/><circle cx="12" cy="12" r="3"/>'),
    logout:icon('<path d="M10 4H5v16h5m4-12 4 4-4 4m-5-4h12"/>')
  };
  menu.innerHTML='<header role="none"><strong id="profileName"></strong><small id="profileRole"></small></header>'+
    [["usage","Uso da conta",""],["mascot","Mostrar mascote","Alt+Shift+M"],["invite","Convide um amigo",""],["settings","Configurações","Ctrl+,"],["admin","Painel do dev-chefe",""],["logout","Sair",""]].map(([action,label,shortcut])=>
      '<button type="button" role="menuitem" tabindex="-1" data-profile="'+action+'">'+icons[action]+'<span class="menu-label">'+label+'</span><kbd>'+shortcut+'</kbd></button>').join("");
  document.body.append(menu);
  const dialog=document.createElement("dialog");dialog.className="profile-dialog";dialog.setAttribute("aria-labelledby","profileDialogTitle");
  dialog.innerHTML='<button type="button" class="dialog-close" aria-label="Fechar">×</button><h2 id="profileDialogTitle"></h2><div id="profileDialogBody"></div>';
  document.body.append(dialog);
  const content=dialog.querySelector("#profileDialogBody");
  const buttons=[...menu.querySelectorAll("button")];
  function closeMenu(focus=false){menu.hidden=true;trigger.setAttribute("aria-expanded","false");if(focus) trigger.focus();}
  function syncAccountPosition(){
    accountBar.hidden=!account;
    const collapsed=!document.body.classList.contains("sidebar-open");
    accountBar.classList.toggle("is-floating",collapsed);
    const parent=collapsed?document.body:sidebar;
    if(accountBar.parentElement!==parent){closeMenu();parent.append(accountBar);}
  }
  new MutationObserver(syncAccountPosition).observe(document.body,{attributes:true,attributeFilter:["class"]});
  function openPanel(name){if(dialog.open)dialog.close();closeMenu();window.dispatchEvent(new CustomEvent("oraculo:open-panel",{detail:name}));}
  function openMenu(){
    if(!account)return;
    if(!menu.hidden){closeMenu();return;}
    const rect=trigger.getBoundingClientRect();menu.hidden=false;
    menu.style.left=Math.max(8,Math.min(rect.left,innerWidth-menu.offsetWidth-8))+"px";
    const top=rect.top>menu.offsetHeight+18?rect.top-menu.offsetHeight-10:rect.bottom+8;
    menu.style.top=Math.max(8,Math.min(top,innerHeight-menu.offsetHeight-8))+"px";
    trigger.setAttribute("aria-expanded","true");buttons[0].focus();
  }
  function show(title,html){
    lastFocus=trigger;closeMenu();
    dialog.classList.remove("settings-mode");dialog.scrollTop=0;
    dialog.querySelector("h2").textContent=title;content.innerHTML=html;
    if(!dialog.open) dialog.showModal();
  }
  async function api(path,options={}){
    const response=await fetch(path,options);const body=await response.json();
    if(!response.ok) throw new Error(body.error||"Não foi possível concluir a solicitação.");
    return body;
  }
  const post=(path,payload)=>api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  async function usage(){
    show("Uso da conta",'<p role="status">Carregando o consumo…</p>');
    const userId=account.id;
    try{
      const data=await api("/api/usage");
      if(!account || account.id!==userId || !dialog.open || dialog.querySelector("h2").textContent!=="Uso da conta")return;
      content.innerHTML='<div class="profile-usage"><article><strong id="ownRequests"></strong><span>Solicitações nas últimas 24h</span></article><article><strong id="ownErrors"></strong><span>Falhas nas últimas 24h</span></article></div><h3>Uso restante</h3><p>A cota restante não é informada ao Oráculo. Os números acima são apenas as solicitações registradas pela sua conta neste computador, incluindo novas tentativas.</p><p>Confira a cota da sua chave no console da Groq.</p><div class="profile-actions"><a class="btn" href="https://console.groq.com/" target="_blank" rel="noopener noreferrer">Abrir Groq</a><button class="btn" id="refreshOwnUsage">Atualizar</button></div>';
      content.querySelector("#ownRequests").textContent=data.requests_24h;
      content.querySelector("#ownErrors").textContent=data.errors_24h;
      content.querySelector("#refreshOwnUsage").onclick=usage;
    }catch(error){if(dialog.open) content.textContent=error.message;}
  }
  function invite(){
    const local=["localhost","127.0.0.1","[::1]"].includes(location.hostname);
    show("Convide um amigo",'<p id="inviteExplanation"></p><textarea id="inviteMessage" aria-label="Mensagem de convite" readonly></textarea><div class="profile-actions"><button class="btn primary" id="copyInvite">Copiar convite</button><button class="btn" id="shareInvite">Compartilhar</button></div><p class="profile-status" role="status"></p>');
    content.querySelector("#inviteExplanation").textContent=local
      ?"Esta instalação roda somente neste computador. O convite orienta seu amigo a pedir acesso ao responsável; compartilhar localhost não dá acesso remoto."
      :"O link exige conexão com este servidor e uma conta autorizada. Compartilhar o convite não cria uma conta.";
    const message=local
      ?"Venha testar o Oráculo! Fale com Felipe para receber acesso e as instruções de instalação. Cada participante precisa de uma conta autorizada. Não compartilhe senhas ou chaves de API."
      :"Venha testar o Oráculo: "+location.origin+"/\nPeça uma conta ao responsável pelo ambiente. O acesso depende da conexão com este servidor.";
    content.querySelector("#inviteMessage").value=message;
    const status=content.querySelector(".profile-status");
    content.querySelector("#copyInvite").onclick=async()=>{
      try{await navigator.clipboard.writeText(message);status.textContent="Convite copiado.";}
      catch{content.querySelector("textarea").select();status.textContent="Selecionei o convite. Use Ctrl+C para copiar.";}
    };
    const share=content.querySelector("#shareInvite");share.hidden=!navigator.share;
    share.onclick=async()=>{try{await navigator.share({title:"Oráculo",text:message});status.textContent="Convite compartilhado.";}catch(error){if(error.name!=="AbortError")status.textContent="Não foi possível compartilhar. Use Copiar convite.";}};
  }
  function settings(){
    const pet=window.OraculoMascot.status();
    show("Configurações",'<p id="profileAccountInfo"></p><h3>Mascote</h3><label class="profile-toggle"><input type="checkbox" id="petVisible"> Mostrar mascote nesta conta</label><label class="profile-toggle"><input type="checkbox" id="petRoaming"> Passear, escalar e descansar pela interface</label><p>Arraste para mover; clique para conversar. O mascote fica sentado enquanto você digita. Atalho: Alt+Shift+M.</p><div class="profile-actions"><button class="btn" id="profileMemories">Gerenciar memórias</button><button class="btn" id="profileIntegrations">Integrações</button></div><h3>Alterar senha</h3><form id="profilePassword"><label>Senha atual<input type="password" name="current" autocomplete="current-password" required></label><label>Nova senha<input type="password" name="next" autocomplete="new-password" minlength="10" required></label><label>Confirme a nova senha<input type="password" name="repeat" autocomplete="new-password" minlength="10" required></label><button class="btn primary" type="submit">Salvar senha</button><p class="profile-status" role="status"></p></form>');
    content.querySelector("#profileAccountInfo").textContent=account.display_name+" · "+(account.role==="owner"?"Dev-chefe":"Administrador");
    content.querySelector("#petVisible").checked=pet.visible;
    content.querySelector("#petRoaming").checked=pet.roaming;
    content.querySelector("#petVisible").onchange=()=>window.OraculoMascot.toggle();
    content.querySelector("#petRoaming").onchange=event=>window.OraculoMascot.setRoaming(event.target.checked);
    content.querySelector("#profileMemories").hidden=!permissions.memory_access;
    content.querySelector("#profileMemories").onclick=()=>openPanel("memories");
    content.querySelector("#profileIntegrations").onclick=()=>openPanel("integrations");
    const system=document.createElement("button");system.type="button";system.className="btn";system.textContent="Sistema";system.id="profileSystem";system.onclick=()=>openPanel("health");
    content.querySelector(".profile-actions").append(system);
    const privacy=document.createElement("p");privacy.textContent="As conversas ficam registradas neste computador. Arquivos só são enviados ao modelo após sua revisão e confirmação.";
    content.querySelector("#profileAccountInfo").after(privacy);
    const form=content.querySelector("form");
    form.onsubmit=async event=>{
      event.preventDefault();const status=form.querySelector(".profile-status"),save=form.querySelector("button");
      const current=form.elements.current.value,next=form.elements.next.value,repeat=form.elements.repeat.value;
      if(next!==repeat){status.textContent="A confirmação da nova senha não confere.";return;}
      save.disabled=true;status.textContent="Salvando…";
      try{await post("/api/change-password",{current_password:current,new_password:next});form.reset();status.textContent="Senha alterada.";}
      catch(error){status.textContent=error.message;}
      finally{save.disabled=false;}
    };
    organizeSettings();
  }
  function organizeSettings(){
    dialog.classList.add("settings-mode");
    const nodes=[...content.children];
    const panels={appearance:document.createElement("section"),pet:document.createElement("section"),
      tools:document.createElement("section"),security:document.createElement("section")};
    let group="security";
    for(const node of nodes){
      if(node.id==="profileAccountInfo")continue;
      if(node.tagName==="H3")group=node.textContent==="Mascote"?"pet":"security";
      if(node.classList.contains("profile-actions"))panels.tools.append(node);
      else panels[group].append(node);
    }
    panels.appearance.innerHTML='<h3>Aparência e leitura</h3><p>Personalize este navegador. As alterações são salvas por conta e aplicadas na hora.</p>'+
      '<label class="setting-row">Tamanho das mensagens<select id="layoutText"><option value="14">Pequeno · 14 px</option><option value="16">Padrão · 16 px</option><option value="18">Grande · 18 px</option><option value="20">Maior · 20 px</option></select></label>'+
      '<label class="setting-row">Largura da conversa<select id="layoutWidth"><option value="760">Focada</option><option value="1000">Equilibrada</option><option value="1400">Ampla</option></select></label>'+
      '<label class="profile-toggle"><input id="layoutCompact" type="checkbox"> Espaçamento compacto entre mensagens</label>'+
      '<label class="profile-toggle"><input id="layoutQuiet" type="checkbox"> Fundo discreto, sem estrelas e nebulosas</label>'+
      '<label class="profile-toggle"><input id="layoutEffects" type="checkbox"> Efeitos e animação de escrita</label>'+
      '<button type="button" class="btn" id="resetLayout">Restaurar aparência padrão</button><p id="layoutStatus" role="status"></p>';
    const heading=document.createElement("h3");heading.textContent="Recursos da conta";panels.tools.prepend(heading);
    const nav=document.createElement("nav");nav.className="settings-nav";nav.setAttribute("aria-label","Seções das configurações");
    const body=document.createElement("div");body.className="settings-content";
    for(const [id,label] of [["appearance","Aparência"],["pet","Mascote"],["tools","Recursos"],["security","Segurança"]]){
      const button=document.createElement("button");button.type="button";button.textContent=label;button.dataset.settings=id;
      button.setAttribute("aria-controls","settings-"+id);button.setAttribute("aria-pressed",String(id==="appearance"));
      const panel=panels[id];panel.id="settings-"+id;panel.hidden=id!=="appearance";
      button.onclick=()=>{
        for(const [key,section] of Object.entries(panels))section.hidden=key!==id;
        nav.querySelectorAll("button").forEach(item=>item.setAttribute("aria-pressed",String(item===button)));
        body.scrollTop=0;
      };
      nav.append(button);body.append(panel);
    }
    const info=content.querySelector("#profileAccountInfo");
    content.replaceChildren(info,nav,body);
    const bindings={text:"layoutText",width:"layoutWidth",compact:"layoutCompact",quiet:"layoutQuiet",effects:"layoutEffects"};
    const refresh=()=>{for(const [key,id] of Object.entries(bindings)){const el=content.querySelector("#"+id);if(el.type==="checkbox")el.checked=layout[key];else el.value=layout[key];}};
    const save=()=>{
      applyLayout();
      try{localStorage.setItem("oraculo-layout-"+account.id,JSON.stringify(layout));content.querySelector("#layoutStatus").textContent="Preferências salvas neste navegador.";}
      catch{content.querySelector("#layoutStatus").textContent="Aplicado, mas o navegador não permitiu salvar as preferências.";}
    };
    for(const [key,id] of Object.entries(bindings))content.querySelector("#"+id).onchange=event=>{
      layout[key]=event.target.type==="checkbox"?event.target.checked:event.target.value;save();
    };
    content.querySelector("#resetLayout").onclick=()=>{layout={...defaults};refresh();save();};
    refresh();
  }
  trigger.addEventListener("click",openMenu);
  menu.addEventListener("click",async event=>{
    const action=event.target.closest("[data-profile]")?.dataset.profile;if(!action)return;
    if(action==="usage")usage();
    if(action==="mascot"){window.OraculoMascot.toggle();closeMenu(true);}
    if(action==="invite")invite();
    if(action==="settings")settings();
    if(action==="admin" && account?.role==="owner")openPanel("admin");
    if(action==="logout"){
      closeMenu();
      try{await post("/api/logout",{});window.dispatchEvent(new CustomEvent("oraculo:account",{detail:{user:null,permissions:{}}}));location.reload();}
      catch(error){show("Sair",'<p role="status"></p>');content.querySelector("p").textContent=error.message;}
    }
  });
  menu.addEventListener("keydown",event=>{
    const available=buttons.filter(button=>!button.hidden);
    const position=available.indexOf(document.activeElement);
    if(event.key==="Escape"){event.preventDefault();closeMenu(true);}
    if(event.key==="Tab")closeMenu();
    if(["ArrowDown","ArrowUp","Home","End"].includes(event.key)){
      event.preventDefault();
      const next=event.key==="Home"?0:event.key==="End"?available.length-1:(position+(event.key==="ArrowDown"?1:-1)+available.length)%available.length;
      available[next].focus();
    }
  });
  document.addEventListener("pointerdown",event=>{if(!menu.contains(event.target)&&!trigger.contains(event.target))closeMenu();});
  dialog.querySelector(".dialog-close").onclick=()=>dialog.close();
  dialog.addEventListener("close",()=>{content.replaceChildren();if(account)lastFocus?.focus();});
  window.addEventListener("resize",()=>closeMenu());
  document.addEventListener("keydown",event=>{
    if(!account || event.repeat)return;
    if(event.altKey && event.shiftKey && event.code==="KeyM"){event.preventDefault();window.OraculoMascot.toggle();}
    if((event.ctrlKey||event.metaKey)&&event.key===","){event.preventDefault();settings();}
  });
  window.addEventListener("oraculo:account",event=>{
    account=event.detail.user;permissions=event.detail.permissions||{};
    if(account)loadLayout();else{layout={...defaults};applyLayout();}
    syncAccountPosition();
    menu.querySelector('[data-profile="admin"]').hidden=account?.role!=="owner";
    closeMenu();
    if(dialog.open)dialog.close();
    menu.querySelector("#profileName").textContent=account?.display_name||"";
    menu.querySelector("#profileRole").textContent=account?(account.role==="owner"?"Dev-chefe":"Administrador"):"";
  });
  window.addEventListener("oraculo:mascot",event=>{
    menu.querySelector('[data-profile="mascot"] .menu-label').textContent=event.detail.visible?"Ocultar mascote":"Mostrar mascote";
    const visible=content.querySelector("#petVisible"),roaming=content.querySelector("#petRoaming");
    if(visible)visible.checked=event.detail.visible;if(roaming)roaming.checked=event.detail.roaming;
  });
})();
