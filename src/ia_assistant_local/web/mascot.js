(() => {
  "use strict";
  const SIZE = {w:76, h:86};
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const root = document.createElement("div");
  root.className = "oracle-pet";
  root.hidden = true;
  root.dataset.state = "sit";
  root.innerHTML = '<button type="button" class="pet-body" aria-label="Mascote Oráculo. Arraste para mover; Enter para conversar; Escape para ocultar." title="Arraste para mover · clique para conversar"><svg viewBox="0 0 76 86" aria-hidden="true"><defs><linearGradient id="petShell" x2="0.8" y2="1"><stop stop-color="#f2eef9"/><stop offset="1" stop-color="#aaa2bf"/></linearGradient><linearGradient id="petVisor" x2="0.8" y2="1"><stop stop-color="#242033"/><stop offset="1" stop-color="#12111c"/></linearGradient></defs><ellipse class="pet-shadow" cx="38" cy="81" rx="24" ry="4" fill="#000"/><g class="pet-facing"><g class="pet-figure"><g class="pet-leg-left"><rect x="24" y="61" width="10" height="17" rx="5" fill="#a19aae"/><rect x="20" y="74" width="17" height="7" rx="3.5" fill="#ded8e9"/></g><g class="pet-leg-right"><rect x="42" y="61" width="10" height="17" rx="5" fill="#a19aae"/><rect x="40" y="74" width="17" height="7" rx="3.5" fill="#ded8e9"/></g><g class="pet-arm-left"><rect x="11" y="39" width="11" height="24" rx="5.5" fill="#c8c0d9"/><circle cx="16.5" cy="60" r="5" fill="#e4dced"/></g><g class="pet-arm-right"><rect x="54" y="39" width="11" height="24" rx="5.5" fill="#c8c0d9"/><circle cx="59.5" cy="60" r="5" fill="#e4dced"/></g><rect x="22" y="39" width="32" height="29" rx="12" fill="url(#petShell)"/><path d="M32 52h12l-6 8z" fill="#8e73c1"/><rect x="35" y="7" width="6" height="13" rx="3" fill="#bfb6d2"/><circle cx="38" cy="8" r="4" fill="#b998ee"/><rect x="13" y="17" width="50" height="34" rx="15" fill="url(#petShell)" stroke="#ebe4f5" stroke-width="1"/><rect x="19" y="23" width="38" height="23" rx="10" fill="url(#petVisor)"/><g class="pet-eyes" fill="#b6a1ef"><rect x="26" y="30" width="5" height="9" rx="2.5"/><rect x="45" y="30" width="5" height="9" rx="2.5"/></g><path d="M35 40q3 2 6 0" stroke="#6f688c" fill="none" stroke-linecap="round"/></g></g></svg></button><span class="pet-thought" aria-hidden="true">z z</span><button type="button" class="pet-dismiss" title="Ocultar mascote" aria-label="Ocultar mascote">×</button>';
  document.body.append(root);
  const button = root.querySelector(".pet-body");
  let account = null, visible = false, roaming = true, frame = 0, previous = 0;
  let x = 0, y = 0, action = null, index = 0, side = 1, drag = null, suppressClick = false;
  let blocked = false, busy = false;
  const clamp = (v,min,max) => Math.min(Math.max(v,min),Math.max(min,max));
  function key(){ return "oraculo:mascot:" + account.id; }
  function read(){ try { return JSON.parse(localStorage.getItem(key()) || "{}"); } catch { return {}; } }
  function persist(){ if(account) try { localStorage.setItem(key(),JSON.stringify({visible,roaming})); } catch {} }
  function notify(){ window.dispatchEvent(new CustomEvent("oraculo:mascot",{detail:{visible,roaming}})); }
  function geometry(){
    const app = document.getElementById("app").getBoundingClientRect();
    const bar = document.getElementById("inputForm").getBoundingClientRect();
    const left = clamp(app.left+12,8,innerWidth-SIZE.w-8);
    const right = Math.max(left,Math.min(innerWidth-SIZE.w-8,app.right-SIZE.w-12));
    const floor = Math.max(0,innerHeight-SIZE.h-6);
    return {left,right,floor,top:Math.min(90,floor),
      seat:{x:clamp(bar.right-SIZE.w-68,left,right),y:clamp(bar.top-SIZE.h+10,0,floor)}};
  }
  function paint(){
    x=clamp(x,0,innerWidth-SIZE.w); y=clamp(y,0,innerHeight-SIZE.h);
    root.style.transform="translate3d("+x+"px,"+y+"px,0)";
  }
  function state(value){
    if(root.dataset.state!==value) root.dataset.state=value;
    root.querySelector(".pet-thought").textContent=value==="think"?"···":"z z";
  }
  function atSeat(value="sit"){ const g=geometry(); x=g.seat.x; y=g.seat.y; paint(); state(value); }
  function begin(value,target,duration,anchor=false){
    action={value,from:{x,y},target,duration,elapsed:0,anchor};
    state(value);
    if(target.x!==x) root.dataset.direction=target.x>x?"right":"left";
  }
  function next(){
    const g=geometry(), edge=side>0?g.right:g.left;
    switch(index++%11){
      case 0: begin("sit",g.seat,4800,true); break;
      case 1: begin("sleep",g.seat,4200,true); break;
      case 2: begin("stretch",g.seat,1150,true); break;
      case 3: begin("hop",{x,y:g.floor},650); break;
      case 4: begin("walk",{x:edge,y:g.floor},Math.max(700,Math.abs(edge-x)/.07)); break;
      case 5: begin("climb",{x:edge,y:Math.max(g.top,g.seat.y-120)},3600); break;
      case 6: begin("hang",{x:edge,y},1800); break;
      case 7: begin("climb",{x:edge,y:g.floor},3200); break;
      case 8: begin("walk",{x:g.seat.x,y:g.floor},Math.max(700,Math.abs(g.seat.x-x)/.07)); break;
      case 9: begin("hop",g.seat,700); break;
      case 10: begin("wave",g.seat,1300,true); side*=-1; break;
    }
  }
  function schedule(){
    if(!frame && visible && !document.hidden && !blocked && !motion.matches) frame=requestAnimationFrame(tick);
  }
  function tick(now){
    frame=0;
    const delta=previous?Math.min(now-previous,64):0; previous=now;
    if(!visible || document.hidden || blocked || motion.matches) return;
    if(!drag){
      const typing = document.activeElement===document.getElementById("inputField");
      if(busy || typing || !roaming){
        atSeat(busy?"think":"sit"); action=null; index=0;
      } else {
        if(!action) next();
        action.elapsed+=delta;
        const t=Math.min(action.elapsed/action.duration,1), p=action.value==="hop"?t*t*(3-2*t):t;
        const target=action.anchor?geometry().seat:action.target;
        x=action.from.x+(target.x-action.from.x)*p;
        y=action.from.y+(target.y-action.from.y)*p;
        if(action.value==="hop") y-=Math.sin(t*Math.PI)*35;
        if(action.anchor){x=target.x;y=target.y;}
        paint();
        if(t===1) action=null;
      }
    }
    schedule();
  }
  function pause(){cancelAnimationFrame(frame);frame=0;previous=0;}
  function setVisible(value){
    visible=Boolean(value && account); root.hidden=!visible;
    pause(); action=null;index=0;drag=null;
    if(visible){atSeat();if(!motion.matches)begin("wave",geometry().seat,1300,true);schedule();}
    persist();notify();
  }
  window.OraculoMascot={
    toggle:()=>setVisible(!visible), hide:()=>setVisible(false),
    setRoaming(value){roaming=Boolean(value);action=null;index=0;persist();notify();schedule();},
    status:()=>({visible,roaming})
  };
  root.querySelector(".pet-dismiss").addEventListener("click",()=>setVisible(false));
  button.addEventListener("pointerdown",event=>{
    if(event.button!==0 || !visible) return;
    drag={id:event.pointerId,originX:event.clientX,originY:event.clientY,x,y,moved:false};
    suppressClick=false;action=null;state("drag");button.setPointerCapture(event.pointerId);
  });
  button.addEventListener("pointermove",event=>{
    if(!drag || event.pointerId!==drag.id) return;
    const dx=event.clientX-drag.originX,dy=event.clientY-drag.originY;
    drag.moved ||= Math.hypot(dx,dy)>5;
    x=drag.x+dx;y=drag.y+dy;paint();
  });
  function drop(event){
    if(!drag || event.pointerId!==drag.id) return;
    suppressClick=drag.moved;drag=null;
    if(button.hasPointerCapture(event.pointerId)) button.releasePointerCapture(event.pointerId);
    const g=geometry();
    if(Math.abs(y-g.seat.y)<85){begin("hop",g.seat,450);index=0;}
    else {begin("hop",{x,y:g.floor},500);index=4;}
    if(motion.matches){state("sit");paint();} else schedule();
  }
  button.addEventListener("pointerup",drop);
  button.addEventListener("pointercancel",drop);
  button.addEventListener("click",()=>{
    if(suppressClick){suppressClick=false;return;}
    document.getElementById("inputField").focus();
    if(!motion.matches){state("wave");} else state("sit");
  });
  button.addEventListener("keydown",event=>{
    if(event.key==="Escape"){event.preventDefault();setVisible(false);document.getElementById("profileTrigger").focus();}
    const delta={ArrowLeft:[-16,0],ArrowRight:[16,0],ArrowUp:[0,-16],ArrowDown:[0,16]}[event.key];
    if(delta){event.preventDefault();pause();action=null;x+=delta[0];y+=delta[1];paint();state("sit");}
  });
  button.addEventListener("blur",schedule);
  window.addEventListener("oraculo:account",event=>{
    pause();account=event.detail.user;action=null;index=0;
    const saved=account?read():{};roaming=saved.roaming!==false;
    visible=Boolean(account && saved.visible);root.hidden=!visible;
    if(visible){atSeat();schedule();}notify();
  });
  new MutationObserver(()=>{
    busy=Boolean(document.getElementById("responseStage").textContent.trim());
  }).observe(document.getElementById("responseStage"),{childList:true,characterData:true,subtree:true});
  function updateBlocking(){
    const nextBlocked=Boolean(document.querySelector(".modal-overlay.show,dialog[open]"));
    if(nextBlocked!==blocked){blocked=nextBlocked;root.classList.toggle("is-paused",blocked);if(blocked) pause();else schedule();}
  }
  new MutationObserver(updateBlocking).observe(document.body,{attributes:true,attributeFilter:["class","open"],subtree:true});
  document.addEventListener("visibilitychange",()=>{root.classList.toggle("is-paused",document.hidden||blocked);if(document.hidden) pause();else schedule();});
  motion.addEventListener("change",()=>{pause();if(visible) atSeat();schedule();});
  window.addEventListener("resize",()=>{if(visible){action=null;index=0;atSeat();schedule();}});
})();
