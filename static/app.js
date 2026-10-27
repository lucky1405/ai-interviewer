let currentInterviewId = null;
let ws = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioCtx = null;

// Page Navigation
function showView(viewId) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(viewId).classList.add('active');
}

// Visual Orbs
function attachOrb(streamOrAudio, orbId, isElement) {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  const src = isElement ? audioCtx.createMediaElementSource(streamOrAudio) : audioCtx.createMediaStreamSource(streamOrAudio);
  src.connect(analyser);
  if (isElement) analyser.connect(audioCtx.destination);
  
  const data = new Uint8Array(analyser.frequencyBinCount);
  const orb = document.getElementById(orbId);
  
  function animate() {
    analyser.getByteFrequencyData(data);
    const avg = data.reduce((a, b) => a + b, 0) / data.length;
    orb.style.transform = `scale(${1 + Math.min(avg / 85, 0.65)})`;
    requestAnimationFrame(animate);
  }
  animate();
}

// 1. Upload Resume & Start
async function handleResumeUpload() {
  const file = document.getElementById('resumeFile').files[0];
  if (!file) return alert("Please select a PDF resume.");

  const btn = document.getElementById('uploadBtn');
  btn.disabled = true;
  btn.innerText = "Analyzing Resume...";

  const fd = new FormData();
  fd.append("resume_file", file);
  fd.append("target_role", document.getElementById('targetRole').value);
  fd.append("provider", document.getElementById('provider').value);
  fd.append("api_key", document.getElementById('apiKey').value);

  try {
    const res = await fetch('/api/v1/upload-resume', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);

    currentInterviewId = data.interview_id;
    document.getElementById('candidateName').innerText = data.candidate_name.split(' ')[0];
    
    showView('view-interview');
    startInterviewSocket();
  } catch (e) {
    alert(e.message);
    btn.disabled = false;
    btn.innerText = "Start Interview";
  }
}

// 2. WebSocket Interview Logic
async function startInterviewSocket() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    attachOrb(stream, 'userOrb', false);
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
  } catch (e) {
    alert("Microphone access is required for the voice interview.");
  }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/interview/${currentInterviewId}`);

  ws.onopen = () => {
    ws.send(JSON.stringify({ 
      type: 'start', 
      provider: document.getElementById('provider').value, 
      api_key: document.getElementById('apiKey').value 
    }));
  };

  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    const chatBox = document.getElementById('chatMessages');

    if (msg.type === 'user_turn' || msg.type === 'ai_turn') {
      const div = document.createElement('div');
      div.className = `bubble ${msg.type === 'ai_turn' ? 'assistant' : 'user'}`;
      div.innerHTML = `<strong>${msg.type === 'ai_turn' ? 'AI' : 'You'}:</strong><br/>${msg.text}`;
      chatBox.appendChild(div);
      chatBox.scrollTop = chatBox.scrollHeight;
    }

    if (msg.type === 'ai_turn') {
      document.getElementById('progressText').innerText = msg.progress;
      document.getElementById('aiStatus').innerText = 'AI Speaking...';

      const audio = new Audio(`data:audio/mp3;base64,${msg.audio_b64}`);
      attachOrb(audio, 'aiOrb', true);
      
      audio.onended = () => {
        document.getElementById('aiStatus').innerText = msg.interview_complete ? 'Interview Finished' : 'Waiting for your answer...';
        if (msg.interview_complete) finishInterview();
      };
      await audio.play();
    }
  };
}

function toggleRecording() {
  const btn = document.getElementById('micBtn');
  if (!isRecording) {
    audioChunks = [];
    mediaRecorder.start();
    isRecording = true;
    btn.classList.add('recording');
    btn.innerText = 'Stop & Send Answer';
    document.getElementById('aiStatus').innerText = 'Listening...';
  } else {
    mediaRecorder.stop();
    isRecording = false;
    btn.classList.remove('recording');
    btn.innerText = 'Click to Speak Answer';
    document.getElementById('aiStatus').innerText = 'Thinking...';

    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const reader = new FileReader();
      reader.onloadend = () => {
        ws.send(JSON.stringify({
          type: 'audio',
          audio_b64: reader.result.split(',')[1],
          provider: document.getElementById('provider').value,
          api_key: document.getElementById('apiKey').value
        }));
      };
      reader.readAsDataURL(blob);
    };
  }
}

// 3. End & Fetch Summary
async function finishInterview() {
  if (ws) ws.close();
  showView('view-summary');
  
  const card = document.getElementById('summaryCard');
  card.innerHTML = '<h2 style="text-align:center; color:var(--primary);">Generating your feedback...</h2><p style="text-align:center; color:var(--muted);">This takes a few seconds.</p>';

  const res = await fetch(`/api/v1/generate-summary/${currentInterviewId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      provider: document.getElementById('provider').value, 
      api_key: document.getElementById('apiKey').value 
    })
  });
  const data = await res.json();
  const s = data.summary;

  card.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
      <h2>Interview Feedback</h2>
      <div class="score-badge">Score: ${data.overall_score}/100</div>
    </div>

    <div class="summary-section">
      <h3 style="margin-bottom: 10px;">Executive Summary</h3>
      <p style="color:var(--muted); line-height: 1.6;">${s.executive_summary}</p>
    </div>

    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="summary-section">
        <h3 style="margin-bottom: 10px;">What You Did Well</h3>
        <ul style="color:var(--emerald); margin-left: 20px; line-height: 1.6;">
          ${(s.key_strengths||[]).map(x => `<li><span style="color:var(--text);">${x}</span></li>`).join('')}
        </ul>
      </div>
      <div class="summary-section">
        <h3 style="margin-bottom: 10px;">Areas for Improvement</h3>
        <ul style="color:var(--danger); margin-left: 20px; line-height: 1.6;">
          ${(s.areas_for_concern||[]).map(x => `<li><span style="color:var(--text);">${x}</span></li>`).join('')}
        </ul>
      </div>
    </div>
  `;
}