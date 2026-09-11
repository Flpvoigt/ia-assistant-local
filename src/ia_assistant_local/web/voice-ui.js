/* Local Kokoro output with browser speech as a resilient fallback. */
(() => {
  "use strict";
  const button = document.getElementById("voiceBtn");
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synthesis = window.speechSynthesis;
  let recognition = null;
  let active = false;
  let listening = false;
  let processing = false;
  let muted = false;
  let finalText = "";
  let restartTimer = 0;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  let audioContext = null;
  let audioSource = null;
  let voiceRequest = null;
  let serverVoice = {ready:false, voice:"pm_alex", engine:"kokoro-onnx", fallback:"browser"};

  const dialog = document.createElement("dialog");
  dialog.className = "voice-dialog";
  dialog.setAttribute("aria-label", "Conversa por voz com o Oráculo");
  dialog.innerHTML = `
    <div class="voice-shell" data-state="idle">
      <div class="voice-aurora" aria-hidden="true"></div>
      <header class="voice-topbar">
        <div class="voice-brand"><span class="voice-brand-mark">O</span><span><small>ORÁCULO VOZ</small><strong>Conversa em tempo real</strong></span></div>
        <div class="voice-top-actions"><span class="voice-engine"><i></i><b>pm_alex</b><em>local</em></span><button class="voice-close" type="button" aria-label="Fechar modo de voz">×</button></div>
      </header>
      <main class="voice-stage">
        <section class="voice-presence" aria-label="Estado da conversa">
          <div class="voice-core-wrap">
            <button class="voice-core" type="button" aria-label="Pausar ou continuar microfone">
              <i class="voice-ring ring-a"></i><i class="voice-ring ring-b"></i><i class="voice-ring ring-c"></i>
              <span class="voice-core-orb"><span class="voice-orb-wave"><i></i><i></i><i></i><i></i><i></i></span></span>
            </button>
            <div class="voice-orbit-label"><i></i><span>CANAL SEGURO</span></div>
          </div>
          <div class="voice-state-copy">
            <small><i class="voice-state-dot"></i><span class="voice-status" role="status">Preparando microfone…</span></small>
            <h2>Fale com o Oráculo</h2>
            <p class="voice-transcript" aria-live="polite">A conversa começa quando você falar.</p>
          </div>
          <div class="voice-level" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        </section>
        <section class="voice-conversation" aria-label="Transcrição da conversa">
          <header><span><small>SESSÃO ATUAL</small><strong>Transcrição ao vivo</strong></span><em>pt-BR</em></header>
          <div class="voice-history" aria-live="polite">
            <div class="voice-history-empty"><span>✦</span><strong>Pronto quando você estiver</strong><p>Fale naturalmente. Suas mensagens e as respostas do Oráculo aparecerão aqui.</p></div>
          </div>
          <div class="voice-privacy"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V8a5 5 0 0 1 10 0v2M6 10h12v10H6z"></path></svg><span>Áudio processado nesta sessão</span></div>
        </section>
      </main>
      <footer class="voice-controls">
        <button class="voice-control voice-mute" type="button" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0M12 18v3"></path></svg><span>Silenciar</span></button>
        <div class="voice-session-meta"><strong>Sessão de voz</strong><span>Toque no núcleo ou no microfone para pausar</span></div>
        <button class="voice-control voice-end" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8c3.6-2.4 7.2-2.4 10.8 0l-2 3.2-2.5-1v3h-1.8v-3l-2.5 1z"></path></svg><span>Encerrar</span></button>
      </footer>
    </div>`;
  document.body.appendChild(dialog);
  const shell = dialog.querySelector(".voice-shell");
  const status = dialog.querySelector(".voice-status");
  const transcript = dialog.querySelector(".voice-transcript");
  const core = dialog.querySelector(".voice-core");
  const history = dialog.querySelector(".voice-history");
  const muteButton = dialog.querySelector(".voice-mute");
  const engineBadge = dialog.querySelector(".voice-engine");

  function setState(state, label) {
    shell.dataset.state = state;
    status.textContent = label;
    button.classList.toggle("is-active", active);
  }

  function clearHistory() {
    history.innerHTML = `<div class="voice-history-empty"><span>✦</span><strong>Pronto quando você estiver</strong><p>Fale naturalmente. Suas mensagens e as respostas do Oráculo aparecerão aqui.</p></div>`;
  }

  function appendTurn(role, text) {
    history.querySelector(".voice-history-empty")?.remove();
    const turn = document.createElement("article");
    turn.className = `voice-turn ${role}`;
    const label = document.createElement("span");
    label.textContent = role === "assistant" ? "Oráculo" : "Você";
    const content = document.createElement("p");
    content.textContent = text;
    turn.append(label, content);
    history.appendChild(turn);
    history.scrollTo({top:history.scrollHeight, behavior:"smooth"});
  }

  function updateMuteControl() {
    muteButton.setAttribute("aria-pressed", String(muted));
    muteButton.querySelector("span").textContent = muted ? "Ativar microfone" : "Silenciar";
    muteButton.classList.toggle("is-muted", muted);
  }

  function clearRestart() {
    window.clearTimeout(restartTimer);
    restartTimer = 0;
  }

  function stopRecognition() {
    clearRestart();
    if(recognition && listening) {
      try { recognition.abort(); } catch(_error) {}
    }
    listening = false;
  }

  function cleanForSpeech(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " bloco de código ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/^\s{0,3}#{1,6}\s+/gm, "")
      .replace(/^\s*[-*+]\s+/gm, "")
      .replace(/[*_~>|]/g, "")
      .replace(/https?:\/\/\S+/g, "link")
      .replace(/\s+/g, " ")
      .trim();
  }

  function portugueseVoice() {
    if(!synthesis) return null;
    const voices = synthesis.getVoices();
    return voices.find(voice => /^pt-BR$/i.test(voice.lang)) ||
      voices.find(voice => /^pt/i.test(voice.lang)) || null;
  }

  async function statusInfo() {
    try {
      const response = await fetch("/api/voice/status", {cache:"no-store"});
      if(response.ok) serverVoice = await response.json();
    } catch(_error) {}
    return {...serverVoice, browser:Boolean(synthesis && window.SpeechSynthesisUtterance)};
  }

  function stopAudio() {
    if(voiceRequest) voiceRequest.abort();
    voiceRequest = null;
    if(audioSource) {
      try { audioSource.stop(); } catch(_error) {}
      audioSource = null;
    }
    if(synthesis) synthesis.cancel();
  }

  function unlockAudio() {
    if(!AudioContext) return null;
    if(!audioContext) audioContext = new AudioContext();
    if(audioContext.state === "suspended") audioContext.resume().catch(()=>{});
    return audioContext;
  }

  function browserSpeech(clean) {
    return new Promise((resolve, reject) => {
      if(!synthesis || !window.SpeechSynthesisUtterance) {
        reject(new Error("Nenhum mecanismo de voz está disponível."));
        return;
      }
      const utterance = new SpeechSynthesisUtterance(clean);
      utterance.lang = "pt-BR";
      utterance.rate = 1.02;
      utterance.pitch = 0.96;
      const voice = portugueseVoice();
      if(voice) utterance.voice = voice;
      utterance.onend = () => resolve("browser");
      utterance.onerror = () => reject(new Error("A voz do navegador falhou."));
      synthesis.speak(utterance);
    });
  }

  async function playStreamChunk(payload, context, request) {
    if(request.signal.aborted) throw new DOMException("Áudio cancelado", "AbortError");
    const raw = atob(payload.audio);
    const bytes = new Uint8Array(raw.length);
    for(let index=0; index<raw.length; index++) bytes[index] = raw.charCodeAt(index);
    const decoded = await context.decodeAudioData(bytes.buffer.slice(0));
    await context.resume();
    await new Promise((resolve, reject) => {
      const source = context.createBufferSource();
      audioSource = source;
      source.buffer = decoded;
      source.connect(context.destination);
      source.onended = () => {
        if(audioSource === source) audioSource = null;
        resolve();
      };
      request.signal.addEventListener("abort", () => {
        try { source.stop(); } catch(_error) {}
      }, {once:true});
      try { source.start(0); }
      catch(error) { reject(error); }
    });
  }

  async function professionalSpeech(clean) {
    stopAudio();
    const context = unlockAudio();
    if(!context) return browserSpeech(clean);
    const request = new AbortController();
    voiceRequest = request;
    let streamed = false;
    try {
      const response = await fetch("/api/voice/stream", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({text:clean}),
        signal:request.signal
      });
      if(!response.ok || !response.body) throw new Error("Kokoro indisponível");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      while(true) {
        const {done, value} = await reader.read();
        pending += decoder.decode(value || new Uint8Array(), {stream:!done});
        const lines = pending.split("\n");
        pending = lines.pop() || "";
        if(done && pending.trim()) lines.push(pending);
        for(const line of lines) {
          if(!line.trim()) continue;
          const payload = JSON.parse(line);
          if(payload.error) throw new Error(payload.error);
          await playStreamChunk(payload, context, request);
          streamed = true;
        }
        if(done) break;
      }
      return "pm_alex";
    } catch(error) {
      if(error.name === "AbortError") throw error;
      if(streamed) throw error;
      return browserSpeech(clean);
    } finally {
      if(voiceRequest === request) voiceRequest = null;
    }
  }

  function scheduleListening(delay = 450) {
    clearRestart();
    if(!active || muted || processing) return;
    restartTimer = window.setTimeout(startListening, delay);
  }

  async function speak(text) {
    const clean = cleanForSpeech(text);
    if(!active) return;
    if(!clean) {
      processing = false;
      scheduleListening();
      return;
    }
    stopRecognition();
    processing = true;
    transcript.textContent = clean;
    appendTurn("assistant", clean);
    setState("speaking", "Oráculo está respondendo com pm_alex");
    try {
      await professionalSpeech(clean);
      if(!active) return;
      processing = false;
      transcript.textContent = "Pode continuar. Estou ouvindo.";
      scheduleListening(350);
    } catch(error) {
      processing = false;
      if(active && error.name !== "AbortError") scheduleListening();
    }
  }

  function makeRecognition() {
    const instance = new SpeechRecognition();
    instance.lang = "pt-BR";
    instance.continuous = false;
    instance.interimResults = true;
    instance.maxAlternatives = 1;
    instance.onstart = () => {
      listening = true;
      muted = false;
      updateMuteControl();
      finalText = "";
      transcript.textContent = "Estou ouvindo…";
      setState("listening", "Ouvindo");
    };
    instance.onresult = event => {
      let interim = "";
      for(let index = event.resultIndex; index < event.results.length; index++) {
        const part = event.results[index][0].transcript;
        if(event.results[index].isFinal) finalText += part;
        else interim += part;
      }
      transcript.textContent = (finalText + " " + interim).trim() || "Estou ouvindo…";
    };
    instance.onerror = event => {
      listening = false;
      if(!active || event.error === "aborted") return;
      if(event.error === "not-allowed" || event.error === "service-not-allowed") {
        muted = true;
        updateMuteControl();
        setState("error", "Permissão de microfone negada");
        transcript.textContent = "Libere o microfone nas permissões do navegador e tente novamente.";
        return;
      }
      if(event.error !== "no-speech") {
        setState("error", "Não consegui ouvir");
        transcript.textContent = "Verifique o microfone e toque no núcleo para tentar novamente.";
      }
    };
    instance.onend = () => {
      listening = false;
      if(!active) return;
      const text = finalText.trim();
      finalText = "";
      if(text) {
        processing = true;
        transcript.textContent = text;
        appendTurn("user", text);
        setState("processing", "Oráculo está pensando");
        window.dispatchEvent(new CustomEvent("oraculo:voice-submit", {detail:{text}}));
      } else if(!processing) {
        scheduleListening(550);
      }
    };
    return instance;
  }

  function startListening() {
    if(!active || muted || processing || listening || !SpeechRecognition) return;
    recognition = makeRecognition();
    try { recognition.start(); }
    catch(_error) { scheduleListening(700); }
  }

  function finish() {
    active = false;
    muted = false;
    processing = false;
    stopRecognition();
    stopAudio();
    button.classList.remove("is-active");
    updateMuteControl();
    if(dialog.open) dialog.close();
  }

  function preview(text) {
    unlockAudio();
    const clean = cleanForSpeech(text);
    if(!clean) return false;
    const resumeAfter = active && dialog.open;
    if(resumeAfter) stopRecognition();
    window.dispatchEvent(new CustomEvent("oraculo:voice-preview-status",{detail:{state:"loading"}}));
    professionalSpeech(clean).then(engine => {
      window.dispatchEvent(new CustomEvent("oraculo:voice-preview-status",{detail:{state:"done",engine}}));
      if(resumeAfter && active) scheduleListening(350);
    }).catch(error => {
      if(error.name !== "AbortError") {
        window.dispatchEvent(new CustomEvent("oraculo:voice-preview-status",{detail:{state:"error"}}));
      }
    });
    return true;
  }

  function open() {
    unlockAudio();
    if(dialog.open) return;
    active = true;
    muted = false;
    processing = false;
    clearHistory();
    updateMuteControl();
    transcript.textContent = SpeechRecognition ? "Autorize o microfone para começar." :
      "Este navegador não oferece reconhecimento de voz. Use Chrome, Edge ou Safari atualizado.";
    setState(SpeechRecognition ? "idle" : "error", SpeechRecognition ? "Preparando microfone…" : "Voz indisponível neste navegador");
    dialog.showModal();
    statusInfo().then(info => {
      const available = info.ready;
      engineBadge.classList.toggle("is-fallback", !available);
      engineBadge.querySelector("b").textContent = available ? "pm_alex" : "voz reserva";
      engineBadge.querySelector("em").textContent = available ? (info.model_variant || "local") : "navegador";
    });
    if(SpeechRecognition) startListening();
  }

  function toggleMicrophone() {
    if(!SpeechRecognition || processing) return;
    if(muted || !listening) {
      muted = false;
      active = true;
      updateMuteControl();
      transcript.textContent = "Pode falar. Estou ouvindo.";
      startListening();
      return;
    }
    muted = true;
    stopRecognition();
    updateMuteControl();
    setState("paused", "Microfone pausado");
    transcript.textContent = "O microfone está pausado.";
  }

  button.addEventListener("click", open);
  dialog.querySelector(".voice-close").addEventListener("click", finish);
  dialog.querySelector(".voice-end").addEventListener("click", finish);
  dialog.addEventListener("cancel", event => { event.preventDefault(); finish(); });
  core.addEventListener("click", toggleMicrophone);
  muteButton.addEventListener("click", toggleMicrophone);
  window.addEventListener("oraculo:voice-state", event => {
    if(!active) return;
    if(event.detail?.state === "processing") {
      processing = true; stopRecognition(); setState("processing", "Oráculo está pensando");
    } else if(event.detail?.state === "error") {
      processing = false; setState("error", "Não foi possível responder");
      transcript.textContent = event.detail.message || "Tente novamente."; scheduleListening(1800);
    }
  });
  window.addEventListener("oraculo:voice-reply", event => speak(event.detail?.text));
  window.addEventListener("oraculo:account", finish);
  window.OraculoVoice = {
    capabilities: {
      recognition:Boolean(SpeechRecognition),
      synthesis:true,
      secure:Boolean(window.isSecureContext)
    },
    status:statusInfo,
    preview,
    stopSpeech:stopAudio,
    open
  };
  statusInfo();
})();
