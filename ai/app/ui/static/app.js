// SSE connection to Python backend
const evtSource = new EventSource("/events");
const messagesEl = document.getElementById("messages");
const portraitEl = document.getElementById("portrait");
const portraitArea = document.getElementById("portrait-area");
const ttsPlayer = document.getElementById("tts-player");
const statusText = document.getElementById("status-text");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

// Track current TTS queue
let ttsQueue = [];
let ttsPlaying = false;
let sending = false;

function addMessage(role, en, zh, tone) {
  const div = document.createElement("div");
  div.className = "message " + role;

  if (role === "monika") {
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.src = "/portrait/" + (tone || "neutral");
    div.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (en) {
    const enEl = document.createElement("div");
    enEl.className = "en";
    enEl.textContent = en;
    bubble.appendChild(enEl);
  }
  if (zh) {
    const zhEl = document.createElement("div");
    zhEl.className = "zh";
    zhEl.textContent = zh;
    bubble.appendChild(zhEl);
  }
  div.appendChild(bubble);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function setPortrait(path, tone) {
  if (path) {
    portraitEl.src = path;
  }
  portraitArea.className = tone === "listening" ? "listening" : "";
}

function playTTS(path) {
  ttsQueue.push(path);
  if (!ttsPlaying) playNext();
}

function playNext() {
  if (ttsQueue.length === 0) { ttsPlaying = false; return; }
  ttsPlaying = true;
  const path = ttsQueue.shift();
  ttsPlayer.src = path;
  ttsPlayer.play().then(() => {
    ttsPlayer.onended = playNext;
  }).catch(() => playNext());
}

function sendMessage() {
  const text = userInput.value.trim();
  if (!text || sending) return;
  sending = true;
  userInput.disabled = true;
  sendBtn.disabled = true;
  addMessage("user", null, text);
  userInput.value = "";
  statusText.textContent = "Monika is thinking...";

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text })
  }).then(r => r.json()).then(data => {
    if (!data.ok) {
      statusText.textContent = data.error || "Error";
    }
  }).catch(err => {
    statusText.textContent = "Connection error";
    console.error(err);
  }).finally(() => {
    sending = false;
    userInput.disabled = false;
    sendBtn.disabled = false;
    userInput.focus();
  });
}

// Input bar handlers
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// SSE event handlers
evtSource.addEventListener("segment", function(e) {
  const d = JSON.parse(e.data);
  setPortrait(d.portrait || "/portrait/neutral", d.tone);
  addMessage("monika", d.en, d.zh, d.tone);
});

evtSource.addEventListener("user_text", function(e) {
  const d = JSON.parse(e.data);
  addMessage("user", null, d.text);
});

evtSource.addEventListener("tts_audio", function(e) {
  const d = JSON.parse(e.data);
  if (d.path) playTTS(d.path);
});

evtSource.addEventListener("state", function(e) {
  const d = JSON.parse(e.data);
  if (d.input_state === "LISTENING") {
    portraitArea.className = "listening";
    statusText.textContent = "Listening...";
  } else if (d.input_state === "SPEAKING") {
    statusText.textContent = "Monika is speaking...";
  } else {
    portraitArea.className = "";
    statusText.textContent = "Monika is here";
  }
});

evtSource.addEventListener("ping", function() {});

evtSource.onerror = function() {
  statusText.textContent = "Reconnecting...";
};

// Focus input on load
userInput.focus();
