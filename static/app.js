import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import {
  browserSessionPersistence,
  getAuth,
  onAuthStateChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signOut,
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";

const $ = (selector) => document.querySelector(selector);
const login = $("#login");
const panel = $("#chatPanel");
const status = $("#status");
const messages = $("#messages");
const classSelect = $("#classSelect");
const SEND_ERROR = "Não consegui consultar a Agenda agora. Tente de novo daqui a pouco ou confira a Agenda manualmente.";

let auth = null;
let user = null;
let sessionId = null;
let busy = false;

const agendaToProfessorClass = {
  "2° TECH D": "2º Tec D",
  "2° TECH E": "2º Tec E",
  "2° TECH F": "2º Tec F",
  "2° TECH G": "2º Tec G",
  "2° TECH H": "2º Tec H",
  "2° TECH I": "2º Tec I",
  "3° TECH AD H": "3º Tec AD H",
  "3° TECH AD I": "3º Tec AD I",
  "3° TECH DS E": "3º Tec DS E",
  "3° TECH DS F": "3º Tec DS F",
  "3° TECH DS G": "3º Tec DS G",
};
const professorToAgendaClass = Object.fromEntries(
  Object.entries(agendaToProfessorClass).map(([agenda, professor]) => [professor, agenda]),
);

function readPreferredClass() {
  try {
    const shared = localStorage.getItem("tech-2d:preferredClass");
    if (shared && professorToAgendaClass[shared]) return professorToAgendaClass[shared];
    return localStorage.getItem("agenda:turma") || null;
  } catch {
    return null;
  }
}

function bubble(text, who) {
  const element = document.createElement("div");
  element.className = `bubble ${who}`;
  element.textContent = text;
  messages.append(element);
  messages.scrollTop = messages.scrollHeight;
  return element;
}

function showAnswer(text) {
  const element = bubble(text, "assistant");
  const linkText = "confira a Agenda manualmente";
  if (!text.includes(linkText)) return element;

  const parts = text.split(linkText);
  element.replaceChildren(document.createTextNode(parts[0]));
  const link = document.createElement("a");
  link.href = "https://tech-2d.github.io/Agenda/";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = linkText;
  element.append(link, document.createTextNode(parts.slice(1).join(linkText)));
  return element;
}

function displayDate(isoDate) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(isoDate || "")) return isoDate || "";
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

function safeActivityUrl(value) {
  try {
    const url = new URL(value);
    if (
      url.protocol === "https:" &&
      url.hostname === "tech-2d.github.io" &&
      url.pathname === "/Agenda/" &&
      url.hash.startsWith("#atividade=")
    ) return url.href;
  } catch {
    // Use the public Agenda as a safe fallback when a row has an invalid identifier.
  }
  return "https://tech-2d.github.io/Agenda/";
}

function showCards(cards) {
  if (!Array.isArray(cards) || cards.length === 0) return;
  const wrapper = document.createElement("div");
  wrapper.className = "cards";

  for (const card of cards) {
    const link = document.createElement("a");
    link.className = "activity-card";
    link.href = safeActivityUrl(card.url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    const title = document.createElement("strong");
    title.textContent = card.title || "Atividade";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = [
      card.type_label || card.type,
      card.subject,
      displayDate(card.date),
      card.time,
    ].filter(Boolean).join(" · ");
    link.append(title, meta);

    if (card.recurrence_summary) {
      const recurrence = document.createElement("div");
      recurrence.className = "meta recurrence";
      recurrence.textContent = `Recorrência cadastrada: ${card.recurrence_summary}`;
      link.append(recurrence);
    }

    if (card.is_general) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Evento geral";
      link.append(badge);
    }
    if (card.was_overridden) {
      const badge = document.createElement("span");
      badge.className = "badge changed";
      badge.textContent = "Ocorrência alterada";
      link.append(badge);
    }
    wrapper.append(link);
  }

  messages.append(wrapper);
  messages.scrollTop = messages.scrollHeight;
}

async function loadClasses() {
  try {
    const token = await user.getIdToken();
    const response = await fetch("/api/classes", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("class catalog unavailable");
    const { classes } = await response.json();
    const preferred = readPreferredClass();
    classSelect.replaceChildren(new Option("Escolha uma turma", ""));
    for (const name of classes) classSelect.add(new Option(name, name));
    classSelect.value = preferred && classes.includes(preferred) ? preferred : "";
  } catch {
    classSelect.replaceChildren(new Option("Turmas indisponíveis", ""));
  }
}

async function loadFirebaseConfig() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) throw new Error("Firebase config unavailable");
    const { firebase } = await response.json();
    if (!firebase.apiKey || !firebase.appId || !firebase.projectId) throw new Error("Firebase config incomplete");
    auth = getAuth(initializeApp(firebase));
    await setPersistence(auth, browserSessionPersistence);
    onAuthStateChanged(auth, async (nextUser) => {
      user = nextUser;
      login.classList.toggle("hidden", !!user);
      panel.classList.toggle("hidden", !user);
      status.textContent = user ? (user.email || "Autenticado") : "Desconectado";
      if (user) await loadClasses();
    });
  } catch {
    $("#loginError").textContent = "Não foi possível carregar a autenticação. Tente novamente mais tarde.";
    $("#loginForm button").disabled = true;
  }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  if (!auth) return;
  const fields = new FormData(event.currentTarget);
  try {
    await signInWithEmailAndPassword(auth, fields.get("email"), fields.get("password"));
  } catch {
    $("#loginError").textContent = "Não foi possível entrar. Confira o e-mail e a senha.";
  }
});

$("#chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !user) return;
  const input = $("#message");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  bubble(message, "user");
  busy = true;
  $("#send").disabled = true;
  const loading = bubble("Consultando…", "assistant");
  try {
    const token = await user.getIdToken();
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        preferred_class: classSelect.value || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    loading.remove();
    if (!response.ok) {
      showAnswer(data.detail || SEND_ERROR);
      return;
    }
    sessionId = data.session_id;
    showAnswer(data.answer || SEND_ERROR);
    showCards(data.cards);
    if (data.remaining_messages !== null && data.remaining_messages !== undefined) {
      $("#quota").textContent = `${data.remaining_messages} mensagens restantes hoje`;
    }
  } catch {
    loading.remove();
    showAnswer(SEND_ERROR);
  } finally {
    busy = false;
    $("#send").disabled = false;
    input.focus();
  }
});

$("#newChat").addEventListener("click", async () => {
  if (sessionId && user) {
    const token = await user.getIdToken();
    await fetch(`/api/session/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  sessionId = null;
  messages.replaceChildren();
  bubble("Nova conversa iniciada. O que você gostaria de consultar?", "assistant");
});

$("#logout").addEventListener("click", async () => {
  if (sessionId && user) {
    const token = await user.getIdToken();
    await fetch(`/api/session/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  sessionId = null;
  if (auth) await signOut(auth);
});

void loadFirebaseConfig();
