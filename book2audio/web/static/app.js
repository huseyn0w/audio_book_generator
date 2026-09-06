"use strict";

// The job state lives on the server, so only the id and the screen live here.
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

// --- voices ---

async function loadVoices() {
  const language = $("language").value;
  const gender = $("gender").value;
  const response = await fetch(`/api/voices?language=${language}`);
  if (!response.ok) return;
  const data = await response.json();
  const select = $("voice");
  const preferred = data.defaults[gender];
  select.innerHTML = "";
  const fallback = document.createElement("option");
  fallback.value = "";
  fallback.textContent = t("upload.defaultVoice");
  select.append(fallback);
  for (const voice of data.voices) {
    if (voice.gender !== gender && voice.gender !== "unknown") continue;
    const option = document.createElement("option");
    option.value = voice.id;
    option.textContent = voice.id + (voice.id === preferred ? t("upload.defaultSuffix") : "");
    select.append(option);
  }
}

// The sample plays right from the page: you should hear the narrator before an
// hour of synthesis is spent on them.
let sample = null;

async function playSample() {
  const button = $("listen");
  const language = $("language").value;
  const voice = $("voice").value || $("voice").options[1]?.value;
  if (!voice) return;

  if (sample) sample.pause();
  button.disabled = true;
  button.textContent = t("upload.preparing");
  try {
    sample = new Audio(`/api/sample?language=${language}&voice=${voice}`);
    await sample.play();
  } catch {
    showError(t("upload.sampleFailed"));
  } finally {
    button.disabled = false;
    button.textContent = t("upload.listen");
  }
}

// --- upload ---

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
    showError(data.detail || t("upload.failed"));
    return;
  }
  jobId = data.id;
  show("progress");
  $("stage").textContent = t("progress.extract");
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

// --- the save folder ---

const CUSTOM = "__custom__";

// A full iCloud folder path takes two lines and still gets cut off. We show the
// short form and leave the full one in the browser tooltip.
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

  const serverFolder = destination ? t("review.serverFolder") : t("review.noCopy");
  const options = [{ label: serverFolder, path: "" }, ...suggestions];
  for (const item of options) {
    const option = document.createElement("option");
    option.value = item.path;
    // The first option is already translated, the rest arrive as keys.
    option.textContent = item.key ? t("review." + item.key) : item.label;
    select.append(option);
  }
  const other = document.createElement("option");
  other.value = CUSTOM;
  other.textContent = t("review.otherFolder");
  select.append(other);

  const hint = $("destination-hint");
  hint.textContent = destination
    ? t("review.defaultFolder", { path: shortPath(destination) })
    : t("review.noDefaultFolder");
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

// --- preview ---

// "0.3 min" reads worse than "a minute", and "95 min" worse than "1 h 35 min".
// The forms agree with "takes about ...", hence the Russian genitive.
function synthTime(minutes) {
  if (minutes < 1) return t("review.underMinute");
  if (minutes < 60) return t("review.minutes", { count: Math.round(minutes) });
  return t("review.hours", {
    hours: Math.floor(minutes / 60),
    minutes: Math.round(minutes % 60),
  });
}

async function openReview() {
  loadDestinations();
  const response = await fetch(`/api/jobs/${jobId}/review`);
  if (!response.ok) return;
  const data = await response.json();

  $("review-title").textContent = data.title || "";
  $("review-size").textContent =
    t("review.size", {
      chars: data.chars.toLocaleString(language),
      minutes: data.minutes,
      synth: synthTime(data.synth_minutes),
    });

  const warning = $("review-warning");
  warning.hidden = !data.warning;
  if (data.warning) {
    const { expected, found, share } = data.warning;
    warning.textContent = t("review.wrongLanguage", {
      expected: t(expected === "ru" ? "review.languageRu" : "review.languageEn"),
      // A separate form: Russian needs «буквы английские», not «буквы английский».
      found: t(found === "ru" ? "review.lettersRu" : "review.lettersEn"),
      share: Math.round(share * 100) + "%",
    });
  }

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
    checkbox.setAttribute("aria-label", t("review.chapterAria", { name: chapter.title || index + 1 }));

    const title = document.createElement("label");
    title.className = "chapter-title";
    title.htmlFor = checkbox.id;
    title.textContent = chapter.title || t("review.chapterFallback", { number: index + 1 });

    const size = document.createElement("span");
    size.className = "subtle mono";
    size.textContent = t("review.minutes", { count: Math.round(chapter.text.length / 15 / 60) });

    head.append(checkbox, title, size);

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = t("review.text");
    const area = document.createElement("textarea");
    area.value = chapter.text;
    area.setAttribute("aria-label", t("review.chapterTextAria", { name: chapter.title || index + 1 }));
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

// --- progress ---

const STAGE_KEYS = { extract: "progress.extract", synth: "progress.synth", assemble: "progress.assemble" };

function watch() {
  if (stream) stream.close();
  stream = new EventSource(`/api/jobs/${jobId}/events`);
  stream.onmessage = (event) => render(JSON.parse(event.data));
  stream.onerror = () => {
    stream.close();
    stream = null;
    // The connection has a limited life, so we reconnect quietly.
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
      job.error || t("failed.cancelled");
    show("failed");
    return;
  }

  show("progress");
  // The heading holds the book title and the line below holds the stage: repeating
  // the same word in two places makes no sense.
  $("progress-title").textContent = job.title || "";
  $("stage").textContent = t(STAGE_KEYS[job.stage] || "progress.preparing");
  if (job.total > 0) {
    const share = job.done / job.total;
    $("bar-fill").style.width = (share * 100).toFixed(1) + "%";
    $("counter").textContent = `${job.done} / ${job.total}`;
    const elapsed = (Date.now() - startedAt) / 1000;
    if (share > 0.02 && startedAt) {
      const left = elapsed / share - elapsed;
      $("eta").textContent = t("progress.eta", { count: Math.ceil(left / 60) });
    }
  }
}

async function showDestination() {
  const box = $("copy-path");
  box.textContent = "";
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) return;
    const { destination } = await response.json();
    box.textContent = destination
      ? t("done.copiedTo", { path: shortPath(destination) })
      : t("done.downloadOnly");
  } catch {
    // The path is a hint. The book is already done, so we stay quiet.
  }
}

// The server hands back numbers and rule keys, and the phrase is built here: the
// interface language need not match the book language.
function reportText(data) {
  const lines = [];
  const clean = data.clean;
  if (clean && clean.chars_before) {
    const percent = Math.round((1 - clean.chars_after / clean.chars_before) * 100) + "%";
    const rules = Object.entries(clean.dropped || {})
      .filter(([, count]) => count)
      .map(([rule, count]) => t("rule." + rule, { count }))
      .join(", ");
    lines.push(rules ? t("done.cleanedRules", { percent, rules }) : t("done.cleaned", { percent }));
  }
  if (data.synth?.failed) lines.push(t("done.failedChunks", { count: data.synth.failed }));
  return lines.join(". ");
}

async function showReport(id) {
  const box = $("done-report");
  box.textContent = "";
  try {
    const response = await fetch(`/api/jobs/${id}/report`);
    if (!response.ok) return;
    const data = await response.json();
    box.textContent = reportText(data);
  } catch {
    // The report is a hint, not the result. We stay quiet, the book is done.
  }
}

function finish(job) {
  $("done-title").textContent = job.title || "";
  $("player").src = `/api/jobs/${jobId}/download`;
  showDestination();
  showReport(jobId);
  show("done");
}

// --- start ---

function reset() {
  if (stream) stream.close();
  stream = null;
  jobId = null;
  $("file").value = "";
  show("upload");
}

function wireLanguage() {
  const select = $("ui-language");
  language = readSavedLanguage();
  select.value = language;
  select.addEventListener("change", () => setLanguage(select.value));
  applyLanguage();
}

document.addEventListener("DOMContentLoaded", () => {
  wireLanguage();
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
      // The failure screen is its own, the upload screen's error box is not visible here.
      $("failed-message").textContent =
        (await response.json()).detail || t("failed.retryFailed");
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
