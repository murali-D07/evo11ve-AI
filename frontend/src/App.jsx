import { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const SUGGESTIONS = ["What do students get at the end?", "How does the program work?", "How much does it cost?"];

const CHUNK_MS = 250; // send a tiny audio frame to the server every 250 ms (true streaming)

const icon = { viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
const MicIcon = () => <svg {...icon}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>;
const StopIcon = () => <svg {...icon}><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" /></svg>;
const SendIcon = () => <svg {...icon}><path d="M12 19V5M5 12l7-7 7 7" /></svg>;

function Orb({ state, onClick }) {
  return (
    <div className={`orb ${state}`} onClick={onClick} role="img" aria-label={`Assistant is ${state}`}>
      <span className="halo" />
      <span className="ring r1" />
      <span className="ring r2" />
      <img className="logo" src="/logo.png" alt="" draggable="false" />
    </div>
  );
}

export default function App() {
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [liveText, setLiveText] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const wsRef = useRef(null);
  const audioRef = useRef(null);
  const conversationRef = useRef(null);
  const sendRef = useRef(null);

  // Keep the newest message (and live transcript) in view.
  useEffect(() => {
    const el = conversationRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, liveText]);

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    setIsSpeaking(false);
  }

  function playSpeech(path) {
    stopAudio();
    const audio = new Audio(path);
    audioRef.current = audio;
    setIsSpeaking(true); // orb switches to "speaking" right away, also covers audio buffering
    const finish = () => { if (audioRef.current === audio) { audioRef.current = null; setIsSpeaking(false); } };
    audio.onended = finish;
    audio.onerror = finish;
    audio.play().catch(finish);
  }

  function startConversation() {
    setStarted(true);
    playSpeech(`${API}/speech/greeting`);
  }

  async function sendMessage(message) {
    const clean = message.trim();
    if (!clean || isThinking) return;
    stopAudio();
    const nextMessages = [...messages, { role: "user", content: clean }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setText("");
    setIsThinking(true);
    try {
      const response = await fetch(`${API}/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: nextMessages }) });
      if (!response.ok || !response.body) throw new Error("The assistant is unavailable.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullReply = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const dataLine = event.split("\n").find((line) => line.startsWith("data: "));
          const typeLine = event.split("\n").find((line) => line.startsWith("event: "));
          if (!dataLine) continue;
          const data = JSON.parse(dataLine.slice(6));
          const type = typeLine?.slice(7);
          if (type === "token") {
            fullReply += data.content;
            setMessages([...nextMessages, { role: "assistant", content: fullReply }]);
          }
          if (type === "error") throw new Error(data.message);
        }
      }
      if (fullReply) playSpeech(`${API}/speech/speak?text=${encodeURIComponent(fullReply)}`);
    } catch (error) {
      setMessages([...nextMessages, { role: "assistant", content: error.message }]);
    } finally {
      setIsThinking(false);
    }
  }
  sendRef.current = sendMessage; // WebSocket callbacks always call the latest version

  function releaseMic() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }

  async function toggleRecording() {
    stopAudio(); // A mic click always stops assistant audio immediately.

    if (isRecording) {
      setIsRecording(false);
      setIsTranscribing(true);
      recorderRef.current?.stop(); // its onstop sends the "stop" message and releases the mic
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setLiveText("");

      const ws = new WebSocket(API.replace(/^http/, "ws") + "/speech/live");
      wsRef.current = ws;

      ws.onopen = () => {
        // One continuous recorder. `start(CHUNK_MS)` emits a small frame every 250 ms.
        const recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (event) => {
          if (event.data.size && ws.readyState === WebSocket.OPEN) ws.send(event.data);
        };
        recorder.onstop = () => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
          releaseMic();
        };
        recorder.start(CHUNK_MS);
        recorderRef.current = recorder;
        setIsRecording(true);
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "partial") {
          // The server sends the whole transcript so far (finished + in-progress words), so replace it.
          setLiveText(msg.text);
        } else if (msg.type === "final") {
          setIsTranscribing(false);
          setLiveText("");
          if (msg.text.trim()) sendRef.current(msg.text);
          else setMessages((current) => [...current, { role: "assistant", content: "I couldn't hear anything. Please try again." }]);
        } else if (msg.type === "error") {
          releaseMic();
          setIsRecording(false);
          setIsTranscribing(false);
          setLiveText("");
          setMessages((current) => [...current, { role: "assistant", content: msg.message }]);
        }
      };

      ws.onerror = () => {
        releaseMic();
        setIsRecording(false);
        setIsTranscribing(false);
        setLiveText("");
        setMessages((current) => [...current, { role: "assistant", content: "Could not connect to live transcription." }]);
      };

      ws.onclose = () => setIsTranscribing(false);
    } catch {
      setMessages((current) => [...current, { role: "assistant", content: "Microphone permission is needed to record audio." }]);
    }
  }

  if (!started) {
    return (
      <main className="landing">
        <section>
          <Orb state="idle" />
          <p className="eyebrow">Evo11ve AI Skills</p>
          <h1>Your program guide, ready when you are.</h1>
          <button onClick={startConversation}>Start conversation</button>
        </section>
      </main>
    );
  }

  const orbState = isRecording ? "listening" : isThinking || isTranscribing ? "thinking" : isSpeaking ? "speaking" : "idle";
  const status = {
    listening: "Listening… tap the mic when you're done",
    thinking: "Thinking…",
    speaking: "Speaking… tap the orb to stop",
    idle: "Ask about the AI Skills Program",
  }[orbState];

  return (
    <main className="app-shell">
      <header><img className="brand-logo" src="/logo.png" alt="" /> Evo11ve AI Skills <small>Assistant</small></header>
      <section className="assistant-panel">
        <Orb state={orbState} onClick={orbState === "speaking" ? stopAudio : undefined} />
        <h1>AI Skills Assistant</h1>
        <p className="status">{status}</p>
        {messages.length === 0 && !isRecording && !liveText && (
          <div className="chips">
            {SUGGESTIONS.map((question) => <button key={question} className="chip" onClick={() => sendMessage(question)}>{question}</button>)}
          </div>
        )}
        <div className="conversation" ref={conversationRef} aria-live="polite">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.role}`}>
              {message.content || <span className="typing"><i /><i /><i /></span>}
            </div>
          ))}
          {(isRecording || liveText) && (
            <div className="message user live">{liveText || "Listening…"}</div>
          )}
        </div>
      </section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); sendMessage(text); }}>
        <button className={`mic ${isRecording ? "recording" : ""}`} type="button" onClick={toggleRecording} disabled={isTranscribing || (isThinking && !isRecording)} aria-label={isRecording ? "Stop recording" : "Record voice message"}>
          {isRecording ? <StopIcon /> : <MicIcon />}
        </button>
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder="Ask a question..." disabled={isThinking || isRecording || isTranscribing} />
        <button className="send" aria-label="Send" disabled={!text.trim() || isThinking || isRecording || isTranscribing}><SendIcon /></button>
      </form>
    </main>
  );
}