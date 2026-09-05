"use strict";

// Состояние задачи живёт на сервере, поэтому здесь только id и экран.
let jobId = null;
let stream = null;
let startedAt = 0;

const $ = (id) => document.getElementById(id);

const SCREENS = ["upload", "review", "progress", "done", "failed"];

function show(name) {
  for (const screen of SCREENS) {
    $("screen-" + screen).classList.toggle("active", screen === name);
  }
}

function showError(message) {
  const box = $("upload-error");
  box.textContent = message;
  box.hidden = false;
}

// --- голоса ---

async function loadVoices() {
  const language = $("language").value;
  const gender = $("gender").value;
  const response = await fetch(`/api/voices?language=${language}`);
  if (!response.ok) return;
  const data = await response.json();
  const select = $("voice");
  const preferred = data.defaults[gender];
  select.innerHTML = '<option value="">по умолчанию</option>';
  for (const voice of data.voices) {
    if (voice.gender !== gender && voice.gender !== "unknown") continue;
    const option = document.createElement("option");
    option.value = voice.id;
    option.textContent = voice.id + (voice.id === preferred ? " (по умолчанию)" : "");
    select.append(option);
  }
}

// Образец играет прямо со страницы: диктора надо услышать до того, как
// на него потрачен час синтеза.
let sample = null;

async function playSample() {
  const button = $("listen");
  const language = $("language").value;
  const voice = $("voice").value || $("voice").options[1]?.value;
  if (!voice) return;

  if (sample) sample.pause();
  button.disabled = true;
  button.textContent = "Готовлю";
  try {
    sample = new Audio(`/api/sample?language=${language}&voice=${voice}`);
    await sample.play();
  } catch {
    showError("не получилось проиграть образец");
  } finally {
    button.disabled = false;
    button.textContent = "Прослушать";
  }
}

// --- загрузка ---

async function upload(file) {
  $("upload-error").hidden = true;
  const body = new FormData();
  body.append("file", file);
  body.append("language", $("language").value);
  body.append("gender", $("gender").value);
  body.append("pages", $("pages").value.trim());

  const response = await fetch("/api/jobs", { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    showError(data.detail || "не удалось загрузить файл");
    return;
  }
  jobId = data.id;
  show("progress");
  $("stage").textContent = "читаю книгу";
  $("counter").textContent = "";
  watch();
}

function wireDropzone() {
  const zone = $("dropzone");
  const input = $("file");

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => {
    if (input.files.length) upload(input.files[0]);
  });

  for (const name of ["dragenter", "dragover"]) {
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add("over");
    });
  }
  for (const name of ["dragleave", "drop"]) {
    zone.addEventListener(name, () => zone.classList.remove("over"));
  }
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) upload(event.dataTransfer.files[0]);
  });
}

// --- папка сохранения ---

const CUSTOM = "__custom__";

// Полный путь к папке в iCloud занимает две строки и всё равно обрезается.
// Показываем короткий вид, полный остаётся в подсказке браузера.
function shortPath(path) {
  const icloud = "/Library/Mobile Documents/com~apple~CloudDocs";
  const home = path.match(/^\/Users\/[^/]+/);
  let shown = path;
  if (home) shown = path.slice(home[0].length);
  if (shown.startsWith(icloud)) return "iCloud Drive" + shown.slice(icloud.length);
  return home ? "~" + shown : path;
}

async function loadDestinations() {
  const select = $("destination");
  if (select.options.length) return;
  const response = await fetch("/api/settings");
  if (!response.ok) return;
  const { destination, suggestions } = await response.json();

  const options = [{ label: "Как задано при запуске", path: "" }, ...suggestions];
  for (const item of options) {
    const option = document.createElement("option");
    option.value = item.path;
    option.textContent = item.label;
    select.append(option);
  }
  const other = document.createElement("option");
  other.value = CUSTOM;
  other.textContent = "Другая папка…";
  select.append(other);

  const hint = $("destination-hint");
  hint.textContent = destination
    ? `по умолчанию ${shortPath(destination)}`
    : "по умолчанию копия никуда не кладётся";
  hint.title = destination || "";

  select.addEventListener("change", () => {
    const custom = select.value === CUSTOM;
    $("destination-custom").hidden = !custom;
    if (custom) $("destination-custom").focus();
  });
}

function chosenDestination() {
  const select = $("destination");
  return select.value === CUSTOM ? $("destination-custom").value.trim() : select.value;
}

// --- предпросмотр ---

// «0.3 мин» читается хуже, чем «минуты», а «95 мин» хуже, чем «1 ч 35 мин».
// Формы согласованы с «займёт около ...», отсюда родительный падеж.
function synthTime(minutes) {
  if (minutes < 1) return "минуты";
  if (minutes < 60) return `${Math.round(minutes)} мин`;
  return `${Math.floor(minutes / 60)} ч ${Math.round(minutes % 60)} мин`;
}

async function openReview() {
  loadDestinations();
  const response = await fetch(`/api/jobs/${jobId}/review`);
  if (!response.ok) return;
  const data = await response.json();

  $("review-title").textContent = data.title || "";
  $("review-size").textContent =
    `${data.chars.toLocaleString("ru")} символов, примерно ${data.minutes} мин звучания, ` +
    `синтез займёт около ${synthTime(data.synth_minutes)}`;

  const warning = $("review-warning");
  warning.textContent = data.warning || "";
  warning.hidden = !data.warning;

  const host = $("chapters");
  host.innerHTML = "";
  data.chapters.forEach((chapter, index) => {
    const block = document.createElement("div");
    block.className = "chapter";

    const head = document.createElement("div");
    head.className = "chapter-head";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = chapter.include !== false;
    checkbox.id = "ch-" + index;
    checkbox.setAttribute("aria-label", "Озвучивать главу " + (chapter.title || index + 1));

    const title = document.createElement("label");
    title.className = "chapter-title";
    title.htmlFor = checkbox.id;
    title.textContent = chapter.title || `Глава ${index + 1}`;

    const size = document.createElement("span");
    size.className = "subtle mono";
    size.textContent = Math.round(chapter.text.length / 15 / 60) + " мин";

    head.append(checkbox, title, size);

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "текст";
    const area = document.createElement("textarea");
    area.value = chapter.text;
    area.setAttribute("aria-label", "Текст главы " + (chapter.title || index + 1));
    details.append(summary, area);

    block.append(head, details);
    host.append(block);
  });

  show("review");
}

function collectReview() {
  return [...$("chapters").children].map((block) => ({
    title: block.querySelector(".chapter-title").textContent,
    text: block.querySelector("textarea").value,
    include: block.querySelector('input[type="checkbox"]').checked,
  }));
}

async function startSynthesis() {
  $("synth").disabled = true;
  await fetch(`/api/jobs/${jobId}/review`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapters: collectReview() }),
  });
  await fetch(`/api/jobs/${jobId}/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      format: $("format").value,
      voice: $("voice").value,
      destination: chosenDestination(),
    }),
  });
  $("synth").disabled = false;
  startedAt = Date.now();
  show("progress");
  watch();
}

// --- прогресс ---

const STAGE_NAMES = { extract: "читаю книгу", synth: "озвучиваю", assemble: "склеиваю" };

function watch() {
  if (stream) stream.close();
  stream = new EventSource(`/api/jobs/${jobId}/events`);
  stream.onmessage = (event) => render(JSON.parse(event.data));
  stream.onerror = () => {
    stream.close();
    stream = null;
    // Соединение живёт ограниченное время, переподключаемся молча.
    setTimeout(watch, 1000);
  };
}

function render(job) {
  if (job.state === "ready_for_review") {
    if (stream) stream.close();
    stream = null;
    openReview();
    return;
  }
  if (job.state === "done") {
    if (stream) stream.close();
    stream = null;
    finish(job);
    return;
  }
  if (job.state === "failed" || job.state === "cancelled") {
    if (stream) stream.close();
    stream = null;
    $("failed-message").textContent =
      job.error || "задача отменена";
    show("failed");
    return;
  }

  show("progress");
  // Заголовок держит название книги, строка ниже — стадию: дублировать одно
  // и то же слово в двух местах бессмысленно.
  $("progress-title").textContent = job.title || "";
  $("stage").textContent = STAGE_NAMES[job.stage] || "готовлю";
  if (job.total > 0) {
    const share = job.done / job.total;
    $("bar-fill").style.width = (share * 100).toFixed(1) + "%";
    $("counter").textContent = `${job.done} / ${job.total}`;
    const elapsed = (Date.now() - startedAt) / 1000;
    if (share > 0.02 && startedAt) {
      const left = elapsed / share - elapsed;
      $("eta").textContent = "осталось примерно " + Math.ceil(left / 60) + " мин";
    }
  }
}

async function showDestination() {
  const box = $("icloud-path");
  box.textContent = "";
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) return;
    const { destination } = await response.json();
    box.textContent = destination ? `Копия лежит в ${destination}` : "Копия никуда не делалась";
  } catch {
    // Путь это справка. Книга уже готова, молчим.
  }
}

async function showReport(id) {
  const box = $("done-report");
  box.textContent = "";
  try {
    const response = await fetch(`/api/jobs/${id}/report`);
    if (!response.ok) return;
    const data = await response.json();
    const lines = [];
    if (data.clean?.summary) lines.push(data.clean.summary);
    if (data.synth?.failed) lines.push(`не озвучилось кусков: ${data.synth.failed}`);
    box.textContent = lines.join(". ");
  } catch {
    // Отчёт это справка, а не результат. Молчим, книга уже готова.
  }
}

function finish(job) {
  $("done-title").textContent = job.title || "";
  $("player").src = `/api/jobs/${jobId}/download`;
  showDestination();
  showReport(jobId);
  show("done");
}

// --- запуск ---

function reset() {
  if (stream) stream.close();
  stream = null;
  jobId = null;
  $("file").value = "";
  show("upload");
}

document.addEventListener("DOMContentLoaded", () => {
  wireDropzone();
  loadVoices();
  $("language").addEventListener("change", loadVoices);
  $("gender").addEventListener("change", loadVoices);
  $("listen").addEventListener("click", playSample);
  $("synth").addEventListener("click", startSynthesis);
  $("back").addEventListener("click", reset);
  $("again").addEventListener("click", reset);
  $("retry").addEventListener("click", reset);
  $("retry-synth").addEventListener("click", async () => {
    if (!jobId) return reset();
    const response = await fetch(`/api/jobs/${jobId}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format: $("format").value,
        voice: $("voice").value,
        destination: chosenDestination(),
      }),
    });
    if (!response.ok) {
      // Экран ошибки свой, блок ошибки экрана загрузки отсюда не виден.
      $("failed-message").textContent =
        (await response.json()).detail || "не получилось перезапустить";
      return;
    }
    watch();
    show("progress");
  });
  $("download").addEventListener("click", () => {
    window.location.href = `/api/jobs/${jobId}/download`;
  });
  $("cancel").addEventListener("click", async () => {
    await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  });
});
