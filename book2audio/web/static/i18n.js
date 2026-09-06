// Язык интерфейса. По умолчанию английский, выбор живёт в localStorage.
// Сервер строк не присылает: он отдаёт данные и устойчивые ключи, подписи
// выбираются здесь. Иначе английский интерфейс сыпал бы русскими ошибками.

const DEFAULT_LANGUAGE = "en";
const LANGUAGE_KEY = "book2audio.ui-language";

const STRINGS = {
"en": {
  "app.tagline": "pdf · epub · fb2",
  "app.languageLabel": "Interface language",
  "app.madeBy": "Made by",

  "upload.title": "Upload a book",
  "upload.drop": "Drop a file here",
  "upload.dropHint": "or click to choose. PDF, EPUB or FB2",
  "upload.dropAria": "Drop a book file here or click to choose one",
  "upload.bookLanguage": "Book language",
  "upload.russian": "Russian",
  "upload.english": "English",
  "upload.voiceKind": "Voice",
  "upload.female": "Female",
  "upload.male": "Male",
  "upload.pages": "Pages",
  "upload.pagesPlaceholder": "whole book",
  "upload.pagesHint": "22-40, PDF only",
  "upload.narrator": "Narrator",
  "upload.defaultVoice": "default",
  "upload.listen": "Listen",
  "upload.preparing": "Preparing",
  "upload.sampleFailed": "could not play the sample",
  "upload.defaultSuffix": " (default)",
  "upload.failed": "could not upload the file",

  "review.title": "Check the text",
  "review.hint": "Synthesis takes a while, so drop the junk now. Untick chapters you do not want, edit the text right here.",
  "review.size": "{chars} characters, about {minutes} min of audio, synthesis takes about {synth}",
  "review.underMinute": "a minute",
  "review.minutes": "{count} min",
  "review.hours": "{hours} h {minutes} min",
  "review.format": "Format",
  "review.m4b": "m4b, one file with chapters",
  "review.mp3": "mp3, a folder per chapter",
  "review.destination": "Save a copy to",
  "review.noCopy": "No copy, download only",
  "review.desktop": "Desktop",
  "review.downloads": "Downloads",
  "review.documents": "Documents",
  "review.otherFolder": "Another folder…",
  "review.customPlaceholder": "/Users/…/Audiobooks",
  "review.customAria": "Path to your own folder",
  "review.defaultFolder": "default is {path}",
  "review.noDefaultFolder": "no copy is made by default",
  "review.synthesize": "Start conversion",
  "review.another": "Another book",
  "review.chapterChars": "{count} characters",
  "review.chapterAria": "Read chapter {name} aloud",
  "review.chapterTextAria": "Text of chapter {name}",
  "review.text": "text",
  "review.chapterFallback": "Chapter {number}",
  "review.serverFolder": "As set when the server started",
  "review.wrongLanguage": "You picked {expected}, but {share} of the letters are {found}. Check the choice: a voice reads one language.",
  "review.languageRu": "Russian",
  "review.languageEn": "English",
  "review.lettersRu": "Russian",
  "review.lettersEn": "English",

  "progress.title": "Working",
  "progress.preparing": "getting ready",
  "progress.extract": "reading the book",
  "progress.synth": "reading aloud",
  "progress.assemble": "putting it together",
  "progress.eta": "about {count} min left",
  "progress.cancel": "Cancel",

  "done.title": "Done",
  "done.download": "Download",
  "done.again": "One more book",
  "done.copiedTo": "A copy is in {path}",
  "done.downloadOnly": "Download it with the button below",
  "done.cleaned": "cleaning removed {percent} of the characters",
  "done.cleanedRules": "cleaning removed {percent} of the characters: {rules}",
  "done.failedChunks": "pieces that did not synthesize: {count}",

  "rule.running_heads": "running heads {count}",
  "rule.page_numbers": "page numbers {count}",
  "rule.figure_captions": "figure captions {count}",
  "rule.listings": "listings and tables {count}",
  "rule.numeric_captions": "numeric captions {count}",
  "rule.footnotes": "footnotes {count}",

  "failed.title": "That did not work",
  "failed.retry": "Try again",
  "failed.another": "Another book",
  "failed.hint": "What is already read aloud comes from the cache. A retry only computes what is missing.",
  "failed.retryFailed": "could not restart",
  "failed.cancelled": "the job was cancelled"
},
"ru": {
  "app.tagline": "pdf · epub · fb2",
  "app.languageLabel": "Язык интерфейса",
  "app.madeBy": "Сделал",

  "upload.title": "Загрузить книгу",
  "upload.drop": "Перетащите файл сюда",
  "upload.dropHint": "или нажмите, чтобы выбрать. PDF, EPUB или FB2",
  "upload.dropAria": "Перетащите файл книги или нажмите, чтобы выбрать",
  "upload.bookLanguage": "Язык книги",
  "upload.russian": "Русский",
  "upload.english": "English",
  "upload.voiceKind": "Голос",
  "upload.female": "Женский",
  "upload.male": "Мужской",
  "upload.pages": "Страницы",
  "upload.pagesPlaceholder": "вся книга",
  "upload.pagesHint": "22-40, только PDF",
  "upload.narrator": "Диктор",
  "upload.defaultVoice": "по умолчанию",
  "upload.listen": "Прослушать",
  "upload.preparing": "Готовлю",
  "upload.sampleFailed": "не получилось проиграть образец",
  "upload.defaultSuffix": " (по умолчанию)",
  "upload.failed": "не удалось загрузить файл",

  "review.title": "Проверьте текст",
  "review.hint": "Синтез займёт время, поэтому мусор лучше убрать сейчас. Снимите галочки с ненужных глав, поправьте текст прямо здесь.",
  "review.size": "{chars} символов, примерно {minutes} мин звучания, синтез займёт около {synth}",
  "review.underMinute": "минуты",
  "review.minutes": "{count} мин",
  "review.hours": "{hours} ч {minutes} мин",
  "review.format": "Формат",
  "review.m4b": "m4b, один файл с главами",
  "review.mp3": "mp3, папка по главам",
  "review.destination": "Куда сохранить копию",
  "review.noCopy": "Без копии, только скачивание",
  "review.desktop": "Рабочий стол",
  "review.downloads": "Загрузки",
  "review.documents": "Документы",
  "review.otherFolder": "Другая папка…",
  "review.customPlaceholder": "/Users/…/Аудиокниги",
  "review.customAria": "Свой путь к папке",
  "review.defaultFolder": "по умолчанию {path}",
  "review.noDefaultFolder": "по умолчанию копия не делается",
  "review.synthesize": "Начать конвертацию",
  "review.another": "Другая книга",
  "review.chapterChars": "{count} символов",
  "review.chapterAria": "Озвучивать главу {name}",
  "review.chapterTextAria": "Текст главы {name}",
  "review.text": "текст",
  "review.chapterFallback": "Глава {number}",
  "review.serverFolder": "Как задано при запуске",
  "review.wrongLanguage": "Выбран {expected} язык, но {share} букв в книге {found}. Проверьте выбор: голос читает на одном языке.",
  "review.languageRu": "русский",
  "review.languageEn": "английский",
  "review.lettersRu": "русские",
  "review.lettersEn": "английские",

  "progress.title": "Работаю",
  "progress.preparing": "готовлю",
  "progress.extract": "читаю книгу",
  "progress.synth": "озвучиваю",
  "progress.assemble": "склеиваю",
  "progress.eta": "осталось примерно {count} мин",
  "progress.cancel": "Отменить",

  "done.title": "Готово",
  "done.download": "Скачать",
  "done.again": "Ещё книга",
  "done.copiedTo": "Копия лежит в {path}",
  "done.downloadOnly": "Заберите книгу кнопкой ниже",
  "done.cleaned": "чистка убрала {percent} символов",
  "done.cleanedRules": "чистка убрала {percent} символов: {rules}",
  "done.failedChunks": "не озвучилось кусков: {count}",

  "rule.running_heads": "колонтитулы {count}",
  "rule.page_numbers": "колонцифры {count}",
  "rule.figure_captions": "подписи к рисункам {count}",
  "rule.listings": "листинги и таблицы {count}",
  "rule.numeric_captions": "числовые подписи {count}",
  "rule.footnotes": "сноски {count}",

  "failed.title": "Не получилось",
  "failed.retry": "Попробовать снова",
  "failed.another": "Другая книга",
  "failed.hint": "Озвученное берётся из кэша, повтор считает только то, что не досчиталось.",
  "failed.retryFailed": "не получилось перезапустить",
  "failed.cancelled": "задача отменена"
}
};

let language = DEFAULT_LANGUAGE;

function readSavedLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return saved in STRINGS ? saved : DEFAULT_LANGUAGE;
  } catch {
    // Приватное окно или запрет на хранение. Английский по умолчанию.
    return DEFAULT_LANGUAGE;
  }
}

function t(key, values = {}) {
  const table = STRINGS[language] || STRINGS[DEFAULT_LANGUAGE];
  let text = table[key] ?? STRINGS[DEFAULT_LANGUAGE][key] ?? key;
  for (const [name, value] of Object.entries(values)) {
    text = text.replaceAll(`{${name}}`, value);
  }
  return text;
}

// Разметка помечена атрибутами, поэтому перерисовка не трогает состояние.
function applyLanguage() {
  document.documentElement.lang = language;
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  }
  for (const node of document.querySelectorAll("[data-i18n-aria]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAria));
  }
  document.dispatchEvent(new CustomEvent("languagechange"));
}

function setLanguage(next) {
  if (!(next in STRINGS)) return;
  language = next;
  try {
    localStorage.setItem(LANGUAGE_KEY, next);
  } catch {
    // Не сохранилось, но на этой странице язык уже сменился.
  }
  applyLanguage();
}
