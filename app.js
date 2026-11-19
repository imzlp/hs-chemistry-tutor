"use strict";

const DATA_ROOT = "data";
const REVIEW_ROOT = "data/review";
const STORAGE = {
  book: "chemTutor.book.v1",
  mode: "chemTutor.mode.v1",
  known: "chemTutor.known.v1",
};

const LABELS = {
  conceptType: {
    core_concept: "核心概念",
    property: "物质性质",
    process: "反应过程",
    method: "方法模型",
    representation: "化学表示",
    application: "应用",
    history: "化学史",
    safety: "实验安全",
    cross_disciplinary: "跨学科",
  },
  formulaKind: {
    molecular_formula: "分子式",
    condensed_formula: "结构简式",
    polymer_formula: "聚合物表示",
    generic_formula: "类别通式",
    ion_formula: "离子式",
    element_symbol: "元素符号",
    indicator_generic: "指示剂通式",
    protected_placeholder: "受保护占位符",
  },
  formulaRole: {
    representative_substance: "代表性物质",
    class_general_formula: "类别通式",
    contrast_example: "对比物种",
    indicator_equilibrium: "指示剂平衡",
    protected_placeholder: "占位符",
    mentioned_species: "相关物种",
  },
  equationDomain: {
    electrochemistry: "电化学",
    organic_chemistry: "有机化学",
    inorganic_chemistry: "无机化学",
    equilibrium_chemistry: "平衡化学",
  },
  equationMethod: {
    machine_mass_charge_check: "原子与电荷校验",
    structural_review: "结构审查",
  },
  relationStatus: {
    unresolved: "关系缺口",
    ambiguous: "存在歧义",
    self_reference: "自引用",
    external_prior: "外部前置",
  },
  relationDisposition: {
    reviewed_mapping: "已审核映射",
    reviewed_external_prior: "外部前置",
    reviewed_missing_concept: "缺少概念节点",
    reviewed_aggregate_label: "聚合标签",
    reviewed_too_broad: "范围过宽",
    automatic_alias_or_exact_match: "自动解析",
    self_reference: "自引用",
    partially_self_referential: "部分自引用",
    ambiguous: "歧义",
    unreviewed_gap: "未审阅缺口",
  },
  extractionOutcome: {
    no_reaction_equation: "确认无反应方程",
    reaction_equations: "补充真实方程",
    mixed_reclassified: "混合内容已拆分",
  },
  difficulty: {
    easy: "基础",
    medium: "中等",
    hard: "较难",
  },
};

const state = {
  sourceManifest: null,
  modelManifest: null,
  formulaManifest: null,
  equationManifest: null,
  concepts: [],
  occurrences: [],
  relations: [],
  pairs: [],
  formulas: [],
  equations: [],
  extractionReviews: [],
  reviewSheet: [],
  relationReviews: [],
  conceptById: new Map(),
  occurrenceById: new Map(),
  occurrenceByConcept: new Map(),
  conceptIdsByBook: new Map(),
  formulaByConcept: new Map(),
  equationByConcept: new Map(),
  extractionByConcept: new Map(),
  pairByConcept: new Map(),
  relationBySource: new Map(),
  relationReviewByLabel: new Map(),
  reviewByConcept: new Map(),
  searchText: new Map(),
  known: new Set(),
  selectedBook: "all",
  activeId: null,
  query: "",
  mode: "student",
  viewEntries: [],
  treeModel: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function uniqueStrings(values) {
  const seen = new Set();
  const output = [];
  for (const value of safeArray(values)) {
    if (value == null) continue;
    const text = String(value).trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    output.push(text);
  }
  return output;
}

function normalize(value) {
  return String(value ?? "").toLowerCase().replace(/\s+/g, " ").trim();
}

function label(mapping, value, fallback = "未标注") {
  return mapping[value] || String(value ?? fallback).replaceAll("_", " ");
}

function pagesText(pages) {
  const values = safeArray(pages).filter((page) => Number.isFinite(Number(page)));
  return values.length ? `p${values.join("-")}` : "页码未提供";
}

function minPage(ref) {
  const pages = safeArray(ref?.pages).map(Number).filter(Number.isFinite);
  return pages.length ? Math.min(...pages) : 99999;
}

function parseChineseNumber(text) {
  const numerals = "零一二三四五六七八九十";
  const match = /第([零一二三四五六七八九十百0-9]+)[章节]/.exec(text || "");
  if (!match) return 9999;
  const value = match[1];
  if (/^\d+$/.test(value)) return Number(value);
  if (value === "十") return 10;
  if (value.startsWith("十")) return 10 + numerals.indexOf(value[1]);
  if (value.includes("十")) {
    const [left, right] = value.split("十");
    return numerals.indexOf(left) * 10 + (right ? numerals.indexOf(right) : 0);
  }
  const index = numerals.indexOf(value);
  return index >= 0 ? index : 9999;
}

function pushMap(map, key, value) {
  if (!map.has(key)) map.set(key, []);
  map.get(key).push(value);
}

function groupBy(items, keyFn) {
  const groups = new Map();
  for (const item of items) {
    const key = keyFn(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return groups;
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`无法加载 ${path}（HTTP ${response.status}）`);
  return response.text();
}

async function fetchJson(path) {
  return JSON.parse(await fetchText(path));
}

async function fetchJsonl(path) {
  const text = await fetchText(path);
  const records = [];
  for (const [index, line] of text.split("\n").entries()) {
    if (!line.trim()) continue;
    try {
      records.push(JSON.parse(line));
    } catch (error) {
      throw new Error(`${path} 第 ${index + 1} 行 JSON 无效：${error.message}`);
    }
  }
  return records;
}

function readStorage(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value == null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 原型允许在禁用存储的浏览器中降级运行。 */
  }
}

function closeMobileNav() {
  document.body.classList.remove("nav-open");
  $("#hamburger")?.setAttribute("aria-expanded", "false");
}

let toastTimer = null;
function toast(message) {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 1800);
}

function renderFatal(error) {
  const message = escapeHTML(error?.message || error);
  $("#tree").innerHTML = `<div class="tree-empty">数据加载失败<br><span class="mono">${message}</span></div>`;
  $("#main").innerHTML = `<div class="error-box"><b>无法启动教学原型</b><p>${message}</p>
    <p>请通过本地 HTTP 服务访问，例如 <code>python3 -m http.server 8000</code>，不要直接双击打开 <code>index.html</code>。</p></div>`;
}

async function boot() {
  $("#main").innerHTML = '<div class="loading">正在载入规范概念与审核台账…</div>';
  try {
    const [
      sourceManifest,
      modelManifest,
      formulaManifest,
      equationManifest,
      concepts,
      occurrences,
      relations,
      pairs,
      formulas,
      equations,
      extractionReviews,
      reviewSheet,
      relationReviews,
    ] = await Promise.all([
      fetchJson(`${DATA_ROOT}/manifest.json`),
      fetchJson(`${DATA_ROOT}/canonical/manifest.json`),
      fetchJson(`${REVIEW_ROOT}/formula-review-manifest.json`),
      fetchJson(`${REVIEW_ROOT}/manifest.json`),
      fetchJsonl(`${DATA_ROOT}/canonical/concepts.jsonl`),
      fetchJsonl(`${DATA_ROOT}/canonical/occurrences.jsonl`),
      fetchJsonl(`${DATA_ROOT}/canonical/relations.jsonl`),
      fetchJsonl(`${DATA_ROOT}/canonical/confusable-pairs.jsonl`),
      fetchJsonl(`${REVIEW_ROOT}/formula-review.jsonl`),
      fetchJsonl(`${REVIEW_ROOT}/equation-review.jsonl`),
      fetchJsonl(`${REVIEW_ROOT}/equation-extraction-review.jsonl`),
      fetchJsonl(`${DATA_ROOT}/canonical/review-sheet.jsonl`),
      fetchJsonl(`${REVIEW_ROOT}/relation-review.jsonl`),
    ]);

    Object.assign(state, {
      sourceManifest,
      modelManifest,
      formulaManifest,
      equationManifest,
      concepts,
      occurrences,
      relations,
      pairs,
      formulas,
      equations,
      extractionReviews,
      reviewSheet,
      relationReviews,
    });

    indexData();
    restorePreferences();
    buildBookPicker();
    bindEvents();
    updateModeButtons();
    routeFromHash(false);
  } catch (error) {
    console.error(error);
    renderFatal(error);
  }
}

function indexData() {
  for (const concept of state.concepts) {
    state.conceptById.set(concept.concept_id, concept);
  }

  for (const occurrence of state.occurrences) {
    state.occurrenceById.set(occurrence.occurrence_id, occurrence);
    pushMap(state.occurrenceByConcept, occurrence.concept_id, occurrence);
    if (!state.conceptIdsByBook.has(occurrence.book_id)) {
      state.conceptIdsByBook.set(occurrence.book_id, new Set());
    }
    state.conceptIdsByBook.get(occurrence.book_id).add(occurrence.concept_id);
  }

  for (const formula of state.formulas) {
    pushMap(state.formulaByConcept, formula.concept_id, formula);
  }
  for (const equation of state.equations) {
    for (const conceptId of safeArray(equation.concept_ids)) {
      pushMap(state.equationByConcept, conceptId, equation);
    }
  }
  for (const review of state.extractionReviews) {
    state.extractionByConcept.set(review.concept_id, review);
  }
  for (const pair of state.pairs) {
    pushMap(state.pairByConcept, pair.left_concept_id, pair);
    pushMap(state.pairByConcept, pair.right_concept_id, pair);
  }
  for (const relation of state.relations) {
    pushMap(state.relationBySource, relation.source_concept_id, relation);
  }
  for (const review of state.relationReviews) {
    state.relationReviewByLabel.set(review.target_label, review);
  }
  for (const row of state.reviewSheet) {
    state.reviewByConcept.set(row.concept_id, row);
  }

  for (const [conceptId, occurrences] of state.occurrenceByConcept) {
    occurrences.sort(compareOccurrences);
    state.occurrenceByConcept.set(conceptId, occurrences);
  }

  for (const [conceptId, formulas] of state.formulaByConcept) {
    formulas.sort((left, right) => {
      const roleOrder = [
        "representative_substance",
        "class_general_formula",
        "contrast_example",
        "indicator_equilibrium",
        "protected_placeholder",
        "mentioned_species",
      ];
      return (
        roleOrder.indexOf(left.role) - roleOrder.indexOf(right.role)
        || left.formula.localeCompare(right.formula)
      );
    });
    state.formulaByConcept.set(conceptId, formulas);
  }

  for (const [conceptId, equations] of state.equationByConcept) {
    equations.sort((left, right) => (
      left.review_set_key.localeCompare(right.review_set_key)
      || left.equation_index - right.equation_index
    ));
    state.equationByConcept.set(conceptId, equations);
  }

  for (const concept of state.concepts) {
    state.searchText.set(concept.concept_id, buildSearchText(concept));
  }
}

function compareOccurrences(left, right) {
  const leftRef = safeArray(left.textbook_refs)[0] || {};
  const rightRef = safeArray(right.textbook_refs)[0] || {};
  return (
    minPage(leftRef) - minPage(rightRef)
    || left.occurrence_id.localeCompare(right.occurrence_id)
  );
}

function buildSearchText(concept) {
  const formulas = safeArray(state.formulaByConcept.get(concept.concept_id))
    .map((item) => [item.formula, item.display_formula, item.note].join(" "));
  const equations = safeArray(state.equationByConcept.get(concept.concept_id))
    .map((item) => [item.display, item.role, item.review_set_title].join(" "));
  return normalize([
    concept.canonical_name,
    ...safeArray(concept.aliases),
    ...safeArray(concept.subtopics),
    concept.definition?.statement,
    concept.definition?.scope,
    ...safeArray(concept.core_ideas),
    ...formulas,
    ...equations,
  ].join(" "));
}

function restorePreferences() {
  const savedMode = readStorage(STORAGE.mode, "student");
  state.mode = savedMode === "teacher" ? "teacher" : "student";

  const books = new Set(["all", ...safeArray(state.sourceManifest.books).map((book) => book.book_id)]);
  const savedBook = readStorage(STORAGE.book, "all");
  state.selectedBook = books.has(savedBook) ? savedBook : "all";

  const known = readStorage(STORAGE.known, []);
  state.known = new Set(
    safeArray(known).filter((id) => state.conceptById.has(id))
  );
}

function buildBookPicker() {
  const select = $("#bookSelect");
  const books = safeArray(state.sourceManifest.books);
  const options = [
    `<option value="all">全部教材 · ${state.concepts.length} 个概念</option>`,
    ...books.map((book) => {
      const count = state.conceptIdsByBook.get(book.book_id)?.size || 0;
      return `<option value="${escapeHTML(book.book_id)}">${escapeHTML(book.book_title)} · ${count} 个概念</option>`;
    }),
  ];
  select.innerHTML = options.join("");
  select.value = state.selectedBook;
}

function bindEvents() {
  $("#bookSelect").addEventListener("change", (event) => {
    setBook(event.target.value);
  });

  $("#searchInput").addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    renderTree();
    renderSidebarStats();
  });

  $("#hamburger").addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    $("#hamburger").setAttribute("aria-expanded", String(open));
  });

  $("#scrim").addEventListener("click", closeMobileNav);
  $("#sidebarClose").addEventListener("click", closeMobileNav);

  $("#brandLink").addEventListener("click", (event) => {
    event.preventDefault();
    showOverview(true);
  });

  $$(".mode-switch button").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });

  $("#tree").addEventListener("click", (event) => {
    const row = event.target.closest("[data-concept-id]");
    if (!row) return;
    openConcept(row.dataset.conceptId, true);
  });

  $("#main").addEventListener("click", (event) => {
    const conceptLink = event.target.closest("[data-concept-id]");
    if (conceptLink) {
      openConcept(conceptLink.dataset.conceptId, true);
      return;
    }

    const bookButton = event.target.closest("[data-book-id]");
    if (bookButton) {
      setBook(bookButton.dataset.bookId);
      return;
    }

    const scrollButton = event.target.closest("[data-scroll]");
    if (scrollButton) {
      const target = document.getElementById(scrollButton.dataset.scroll);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    const actionButton = event.target.closest("[data-action]");
    if (actionButton) {
      const action = actionButton.dataset.action;
      if (action === "copy-link") copyCurrentLink();
      if (action === "toggle-known" && state.activeId) toggleKnown(state.activeId);
      return;
    }

    const pagerButton = event.target.closest("[data-nav-concept]");
    if (pagerButton) openConcept(pagerButton.dataset.navConcept, true);
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isTyping = target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement;
    if (event.key === "/" && !isTyping) {
      event.preventDefault();
      $("#searchInput").focus();
    }
    if (event.key === "Escape") {
      closeMobileNav();
      if (document.activeElement === $("#searchInput")) $("#searchInput").blur();
    }
  });

  window.addEventListener("popstate", () => routeFromHash(false));
}

function routeFromHash(showHomeWhenEmpty = false) {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (id && state.conceptById.has(id)) {
    openConcept(id, false);
    return;
  }
  if (showHomeWhenEmpty || !id || !state.conceptById.has(id)) showOverview(false);
}

function updateModeButtons() {
  $$(".mode-switch button").forEach((button) => {
    const active = button.dataset.mode === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function setMode(mode) {
  if (mode !== "student" && mode !== "teacher") return;
  state.mode = mode;
  writeStorage(STORAGE.mode, mode);
  updateModeButtons();
  renderMain();
}

function setBook(bookId) {
  if (bookId !== "all" && !state.conceptIdsByBook.has(bookId)) return;
  state.selectedBook = bookId;
  writeStorage(STORAGE.book, bookId);
  $("#bookSelect").value = bookId;

  if (state.activeId && !conceptInBook(state.activeId, bookId)) {
    state.activeId = null;
    history.pushState(null, "", "#");
  }

  renderTree();
  renderSidebarStats();
  renderMain();
  closeMobileNav();
}

function showOverview(pushHistory = false) {
  state.activeId = null;
  if (pushHistory) history.pushState(null, "", "#");
  renderTree();
  renderSidebarStats();
  renderOverview();
  window.scrollTo({ top: 0, behavior: "smooth" });
  closeMobileNav();
}

function openConcept(conceptId, pushHistory = true) {
  const concept = state.conceptById.get(conceptId);
  if (!concept) return;

  if (state.selectedBook !== "all" && !conceptInBook(conceptId, state.selectedBook)) {
    const bookId = primaryBookForConcept(concept);
    if (bookId) {
      state.selectedBook = bookId;
      writeStorage(STORAGE.book, bookId);
      $("#bookSelect").value = bookId;
    }
  }

  state.activeId = conceptId;
  if (pushHistory && location.hash !== `#${conceptId}`) {
    history.pushState(null, "", `#${conceptId}`);
  }
  renderTree();
  renderSidebarStats();
  renderConcept(concept);
  window.scrollTo({ top: 0, behavior: "smooth" });
  closeMobileNav();
}

function primaryBookForConcept(concept) {
  const occurrences = safeArray(state.occurrenceByConcept.get(concept.concept_id));
  const primary = occurrences.find(
    (occurrence) => occurrence.occurrence_id === concept.provenance?.primary_explicit_occurrence_id
  );
  return (primary || occurrences[0])?.book_id || null;
}

function occurrencesForConcept(conceptId) {
  return safeArray(state.occurrenceByConcept.get(conceptId));
}

function conceptInBook(conceptId, bookId) {
  if (bookId === "all") return true;
  return occurrencesForConcept(conceptId).some((occurrence) => occurrence.book_id === bookId);
}

function occurrenceForScope(concept) {
  const occurrences = occurrencesForConcept(concept.concept_id);
  if (!occurrences.length) return null;
  if (state.selectedBook !== "all") {
    const inBook = occurrences.filter((occurrence) => occurrence.book_id === state.selectedBook);
    const primary = inBook.find(
      (occurrence) => occurrence.occurrence_id === concept.provenance?.primary_explicit_occurrence_id
    );
    return primary || inBook[0] || occurrences[0];
  }
  return occurrences.find(
    (occurrence) => occurrence.occurrence_id === concept.provenance?.primary_explicit_occurrence_id
  ) || occurrences[0];
}

function searchMatches(concept) {
  if (!state.query) return true;
  const haystack = state.searchText.get(concept.concept_id) || "";
  const tokens = normalize(state.query).split(/\s+/).filter(Boolean);
  return tokens.every((token) => haystack.includes(token));
}

function buildTreeModel() {
  const bookOrder = new Map(
    safeArray(state.sourceManifest.books).map((book, index) => [book.book_id, index])
  );
  const groups = new Map();

  for (const concept of state.concepts) {
    if (!conceptInBook(concept.concept_id, state.selectedBook) || !searchMatches(concept)) {
      continue;
    }

    const occurrence = occurrenceForScope(concept);
    if (!occurrence) continue;
    const ref = safeArray(occurrence.textbook_refs)[0] || {};
    const bookId = ref.book_id || occurrence.book_id || "unknown";
    const bookTitle = ref.book_title || occurrence.book_title || "未标注教材";
    const chapterTitle = ref.chapter || "未标注章节";
    const sectionTitle = ref.section || "未标注小节";
    const rootKey = state.selectedBook === "all" ? `book:${bookId}` : "scope";

    if (!groups.has(rootKey)) {
      groups.set(rootKey, {
        key: rootKey,
        title: state.selectedBook === "all" ? bookTitle : "",
        order: state.selectedBook === "all" ? (bookOrder.get(bookId) ?? 999) : 0,
        chapters: new Map(),
      });
    }
    const root = groups.get(rootKey);
    const chapterKey = `${rootKey}|chapter:${chapterTitle}`;
    if (!root.chapters.has(chapterKey)) {
      root.chapters.set(chapterKey, {
        key: chapterKey,
        title: chapterTitle,
        order: parseChineseNumber(chapterTitle),
        page: minPage(ref),
        sections: new Map(),
      });
    }
    const chapter = root.chapters.get(chapterKey);
    chapter.page = Math.min(chapter.page, minPage(ref));

    const sectionKey = `${chapterKey}|section:${sectionTitle}`;
    if (!chapter.sections.has(sectionKey)) {
      chapter.sections.set(sectionKey, {
        key: sectionKey,
        title: sectionTitle,
        order: parseChineseNumber(sectionTitle),
        page: minPage(ref),
        concepts: [],
      });
    }
    const section = chapter.sections.get(sectionKey);
    section.page = Math.min(section.page, minPage(ref));
    section.concepts.push({
      concept,
      occurrence,
      ref,
      page: minPage(ref),
      rootKey,
      chapterKey,
      sectionKey,
    });
  }

  const roots = [...groups.values()]
    .sort((left, right) => left.order - right.order || left.title.localeCompare(right.title))
    .map((root) => {
      root.chapters = [...root.chapters.values()]
        .sort((left, right) => left.order - right.order || left.page - right.page || left.title.localeCompare(right.title))
        .map((chapter) => {
          chapter.sections = [...chapter.sections.values()]
            .sort((left, right) => left.order - right.order || left.page - right.page || left.title.localeCompare(right.title))
            .map((section) => {
              section.concepts.sort(
                (left, right) => left.page - right.page
                  || left.concept.canonical_name.localeCompare(right.concept.canonical_name)
              );
              return section;
            });
          return chapter;
        });
      return root;
    });

  const entries = roots.flatMap((root) => root.chapters.flatMap(
    (chapter) => chapter.sections.flatMap((section) => section.concepts)
  ));
  state.viewEntries = entries;
  state.treeModel = { roots, mode: state.selectedBook === "all" ? "books" : "chapters" };
  return state.treeModel;
}

function openDetailsSet() {
  return new Set(
    $$("#tree details[open]").map((element) => element.dataset.key)
  );
}

function pathKeysForActive() {
  if (!state.activeId) return new Set();
  const entry = state.viewEntries.find((item) => item.concept.concept_id === state.activeId);
  if (!entry) return new Set();
  return new Set([entry.rootKey, entry.chapterKey, entry.sectionKey]);
}

function renderTree() {
  const openKeys = openDetailsSet();
  const model = buildTreeModel();
  const activePath = pathKeysForActive();
  if (!model.roots.length) {
    $("#tree").innerHTML = '<div class="tree-empty">没有匹配的概念。请尝试更短的关键词或切换教材。</div>';
    return;
  }

  const shouldOpen = (key, fallback = false) => (
    Boolean(state.query)
    || activePath.has(key)
    || openKeys.has(key)
    || fallback
  );

  const renderConceptRow = (entry) => {
    const concept = entry.concept;
    const active = concept.concept_id === state.activeId;
    const known = state.known.has(concept.concept_id);
    return `<button class="concept-row ${active ? "active" : ""}" data-concept-id="${escapeHTML(concept.concept_id)}"
      title="${escapeHTML(concept.canonical_name)} · ${escapeHTML(entry.ref.chapter || "")}">
      <span class="status-dot ${known ? "known" : ""}" aria-hidden="true"></span>
      <span class="name">${escapeHTML(concept.canonical_name)}</span>
      <span class="page">${escapeHTML(pagesText(entry.ref.pages))}</span>
    </button>`;
  };

  const renderSection = (section) => `<details class="tree-section" data-key="${escapeHTML(section.key)}"
      ${shouldOpen(section.key) ? "open" : ""}>
      <summary><span class="tree-summary">${escapeHTML(section.title)}
        <span class="count">${section.concepts.length}</span></span></summary>
      <div class="concept-list">${section.concepts.map(renderConceptRow).join("")}</div>
    </details>`;

  const renderChapter = (chapter, index) => `<details class="tree-chapter" data-key="${escapeHTML(chapter.key)}"
      ${shouldOpen(chapter.key, state.selectedBook !== "all" && index === 0) ? "open" : ""}>
      <summary><span class="tree-summary">${escapeHTML(chapter.title)}
        <span class="count">${chapter.sections.reduce((sum, section) => sum + section.concepts.length, 0)}</span>
      </span></summary>
      ${chapter.sections.map(renderSection).join("")}
    </details>`;

  const html = model.mode === "books"
    ? model.roots.map((root) => `<details class="tree-book" data-key="${escapeHTML(root.key)}"
        ${shouldOpen(root.key) ? "open" : ""}>
        <summary><span class="tree-summary">${escapeHTML(root.title)}
          <span class="count">${root.chapters.reduce((sum, chapter) => sum
            + chapter.sections.reduce((inner, section) => inner + section.concepts.length, 0), 0)}</span>
        </span></summary>
        ${root.chapters.map(renderChapter).join("")}
      </details>`).join("")
    : model.roots.flatMap((root) => root.chapters).map(renderChapter).join("");

  $("#tree").innerHTML = html;
  requestAnimationFrame(() => {
    $("#tree .concept-row.active")?.scrollIntoView?.({ block: "nearest" });
  });
}

function scopeStats() {
  let conceptIds;
  if (state.selectedBook === "all") {
    conceptIds = new Set(state.concepts.map((concept) => concept.concept_id));
  } else {
    conceptIds = state.conceptIdsByBook.get(state.selectedBook) || new Set();
  }
  const published = new Set(state.viewEntries.map((entry) => entry.concept.concept_id));
  const known = [...conceptIds].filter((id) => state.known.has(id)).length;
  const openIssues = [...conceptIds].filter(
    (id) => safeArray(state.conceptById.get(id)?.quality?.open_issues).length > 0
  ).length;
  const occurrenceCount = state.occurrences.filter(
    (occurrence) => state.selectedBook === "all" || occurrence.book_id === state.selectedBook
  ).length;
  return {
    conceptCount: conceptIds.size,
    visibleCount: published.size,
    known,
    openIssues,
    occurrenceCount,
  };
}

function renderSidebarStats() {
  const stats = scopeStats();
  const scopeTitle = state.selectedBook === "all"
    ? "全部教材"
    : state.sourceManifest.books.find((book) => book.book_id === state.selectedBook)?.book_title || "当前教材";
  const percent = stats.conceptCount ? Math.round((stats.known / stats.conceptCount) * 100) : 0;
  $("#sidebarStats").innerHTML = `
    <div class="scope-label">${escapeHTML(scopeTitle)}</div>
    <div class="scope-stats"><strong>${stats.visibleCount}</strong><span>/ ${stats.conceptCount} 个规范概念</span></div>
    <div class="scope-meta">
      <span>${stats.occurrenceCount} 条教材出现</span>
      <span>${stats.openIssues} 个含开放问题</span>
      ${state.query ? `<span>搜索：${escapeHTML(state.query)}</span>` : ""}
    </div>
    <div class="progress-track"><span style="width:${percent}%"></span></div>
    <div class="progress-label"><span>本机学习进度</span><span>${stats.known} 已学习 · ${percent}%</span></div>`;
}

function renderMain() {
  if (state.activeId) {
    const concept = state.conceptById.get(state.activeId);
    if (concept) {
      renderConcept(concept);
      return;
    }
  }
  renderOverview();
}

function renderOverview() {
  const model = state.modelManifest;
  const books = safeArray(state.sourceManifest.books);
  const teacher = state.mode === "teacher";
  const highPriority = state.reviewSheet
    .filter((row) => row.review_priority === "high")
    .sort((left, right) => left.canonical_name.localeCompare(right.canonical_name))
    .slice(0, teacher ? 8 : 0);

  const bookCards = books.map((book, index) => {
    const conceptCount = state.conceptIdsByBook.get(book.book_id)?.size || 0;
    return `<button class="book-card" data-book-id="${escapeHTML(book.book_id)}">
      <span class="num">${String(index + 1).padStart(2, "0")}</span>
      <span class="name">${escapeHTML(book.book_title)}
        <span class="sub">${conceptCount} 个规范概念 · ${book.kp_count} 条教材出现</span>
      </span>
      <span>→</span>
    </button>`;
  }).join("");

  const priority = highPriority.length
    ? `<section class="overview-panel">
        <h2>教师优先复核</h2>
        <p>来自全量复核工作表中的高优先级概念；优先级不等于事实错误。</p>
        <div class="priority-list">${highPriority.map((row, index) => `
          <button class="priority-item" data-concept-id="${escapeHTML(row.concept_id)}">
            <span class="rank">${String(index + 1).padStart(2, "0")}</span>
            <span class="body"><b>${escapeHTML(row.canonical_name)}</b>
              <small>${escapeHTML((row.issue_codes || []).join(" · ") || "等待人工复核")}</small>
            </span>
          </button>`).join("")}</div>
      </section>`
    : "";

  $("#main").innerHTML = `<div class="content">
    <section class="hero">
      <div class="eyebrow">High School Chemistry · Teaching Prototype</div>
      <h1>从教材知识点，走向可解释的学习路径</h1>
      <p>当前原型直接读取规范概念、公式审核、方程审核与关系台账。每个结论都保留来源 occurrence 和审核边界，不用流畅文案掩盖证据缺口。</p>
      <div class="hero-actions">
        <button class="button primary" data-book-id="${escapeHTML(books[0]?.book_id || "all")}">从必修第一册开始</button>
        <button class="button" data-action="focus-search">搜索概念、化学式或方程</button>
        <button class="button" data-mode-switch="teacher">切换教师视角</button>
      </div>
    </section>

    <div class="overview-grid">
      <div class="metric"><strong>${model.canonical_concepts}</strong><span>规范概念<br>由 ${model.source_occurrences} 条教材出现归并</span></div>
      <div class="metric"><strong>${state.formulaManifest.formula_reviews}</strong><span>公式审核记录<br>${state.formulaManifest.canonical_concepts_with_formulas} 个概念含化学式</span></div>
      <div class="metric"><strong>${state.equationManifest.equations}</strong><span>方程审核记录<br>${state.equationManifest.review_sets} 组反应情境</span></div>
      <div class="metric"><strong>${model.relations.resolved}</strong><span>已解析关系<br>仍有 ${model.relation_review.unreviewed_gap_labels} 个缺口标签</span></div>
    </div>

    <div class="section-stack">
      <section class="overview-panel">
        <h2>按教材进入</h2>
        <p>目录来自每条规范概念的主教材出现记录，可继续在左侧展开章节。</p>
        <div class="book-grid">${bookCards}</div>
      </section>

      ${priority}

      <section class="overview-panel">
        <h2>这个原型能做什么</h2>
        <p>不是自动答题器，而是把结构化知识以可追溯方式交付给教学活动。</p>
        <div class="quality-grid">
          <div class="quality-item"><b>规范概念检索</b><span>按概念名、别名、子主题、定义、化学式和方程式联合搜索。</span></div>
          <div class="quality-item"><b>教学路径</b><span>前置关系可跳转，易混概念并列比较，未解析关系显式保留。</span></div>
          <div class="quality-item"><b>证据优先</b><span>每个概念展示教材出现记录、页码来源、开放问题和审核状态。</span></div>
        </div>
      </section>

      <section class="overview-panel">
        <h2>当前数据边界</h2>
        <p>以下不是界面提示语，而是知识库本身的状态。</p>
        <div class="quality-grid">
          <div class="quality-item"><b>${model.canonical_concepts - model.quality.concepts_with_open_issues} / ${model.canonical_concepts}</b><span>没有显式开放问题的概念；开放问题不等同于事实错误。</span></div>
          <div class="quality-item"><b>0</b><span>已人工签字确认的概念。全部仍为 machine_reviewed。</span></div>
          <div class="quality-item"><b>0</b><span>已验证的出版社、版次、ISBN 与教材原文。</span></div>
        </div>
      </section>
    </div>
  </div>`;

  const focusSearch = $('[data-action="focus-search"]', $("#main"));
  if (focusSearch) {
    focusSearch.addEventListener("click", () => $("#searchInput").focus());
  }
  const teacherSwitch = $('[data-mode-switch="teacher"]', $("#main"));
  if (teacherSwitch) {
    teacherSwitch.addEventListener("click", () => setMode("teacher"));
  }
}

function renderConcept(concept) {
  const occurrences = occurrencesForConcept(concept.concept_id).sort(compareOccurrences);
  const primary = occurrenceForScope(concept);
  const primaryRef = safeArray(primary?.textbook_refs)[0] || {};
  const formulas = safeArray(state.formulaByConcept.get(concept.concept_id));
  const equations = safeArray(state.equationByConcept.get(concept.concept_id));
  const extraction = state.extractionByConcept.get(concept.concept_id);
  const relationRows = safeArray(state.relationBySource.get(concept.concept_id));
  const pairs = safeArray(state.pairByConcept.get(concept.concept_id));
  const teacher = state.mode === "teacher";
  const known = state.known.has(concept.concept_id);
  const review = state.reviewByConcept.get(concept.concept_id);
  const openIssues = safeArray(concept.quality?.open_issues);
  const issues = safeArray(concept.quality?.issue_details);
  const toc = [];

  const definitionCard = renderDefinitionCard(concept);
  if (definitionCard) toc.push(["sec-core", "核心定义"]);
  if (formulas.length) toc.push(["sec-formulas", `化学式 ${formulas.length}`]);
  if (equations.length || extraction) toc.push(["sec-equations", "反应方程"]);

  const teachingCard = renderTeachingCard(concept);
  if (teachingCard) toc.push(["sec-teaching", "教学讲解"]);
  if (safeArray(concept.misconceptions).length) toc.push(["sec-misconceptions", "易错辨析"]);
  toc.push(["sec-assessment", "复习检查"]);
  const relationsCard = renderRelationsCard(concept, relationRows, pairs);
  if (relationsCard) toc.push(["sec-relations", "知识关系"]);
  toc.push(["sec-evidence", "来源证据"]);

  const chips = [
    `<span class="chip brand">${escapeHTML(label(LABELS.conceptType, concept.concept_type))}</span>`,
    `<span class="chip">${escapeHTML(concept.curriculum?.module || "高中化学")}</span>`,
    `<span class="chip info">机器审核</span>`,
    `<span class="chip ${openIssues.length ? "warn" : "ok"}">${openIssues.length} 个开放问题</span>`,
  ];
  if (teacher && review?.review_priority === "high") {
    chips.push('<span class="chip danger">优先复核</span>');
  }

  const pager = renderPager(concept.concept_id);

  $("#main").innerHTML = `<div class="content">
    <header class="concept-head">
      <div class="breadcrumb">
        <span>${escapeHTML(primaryRef.book_title || primary?.book_title || "教材")}</span>
        <span class="sep">/</span><span>${escapeHTML(primaryRef.chapter || "章节未标注")}</span>
        <span class="sep">/</span><span>${escapeHTML(primaryRef.section || "小节未标注")}</span>
        <span class="sep">/</span><span>${escapeHTML(pagesText(primaryRef.pages))}</span>
      </div>
      <h1 class="concept-title">${escapeHTML(concept.canonical_name)}</h1>
      <div class="chips">${chips.join("")}</div>
      <div class="concept-actions">
        <button class="button ${known ? "known" : ""}" data-action="toggle-known">
          ${known ? "✓ 已标记学习" : "标记为已学习"}
        </button>
        <button class="button" data-action="copy-link">复制本页链接</button>
      </div>
      <div class="evidence-banner">
        <span class="icon">!</span>
        <span><b>证据状态：AI 教材摘要，未人工审定。</b>
        页码来自现有摘要，出版社、版次、ISBN 和教材原文均未核验；机器配平与公式分类也不能替代教师判断。</span>
      </div>
    </header>

    <nav class="toc">${toc.map(([id, text]) => `<button data-scroll="${id}">${escapeHTML(text)}</button>`).join("")}</nav>
    ${definitionCard}
    ${formulas.length ? renderFormulaCard(formulas) : ""}
    ${equations.length || extraction ? renderEquationCard(equations, extraction, teacher) : ""}
    ${teachingCard}
    ${safeArray(concept.misconceptions).length ? renderMisconceptionCard(concept) : ""}
    ${renderAssessmentCard(concept)}
    ${relationsCard || ""}
    ${renderEvidenceCard(concept, occurrences, teacher)}
    ${pager}
  </div>`;
}

function renderCard(id, icon, title, body, side = "") {
  return `<section class="card" id="${id}">
    <div class="card-head"><span class="card-icon">${icon}</span><h2 class="card-title">${escapeHTML(title)}</h2>
      ${side ? `<span class="side">${escapeHTML(side)}</span>` : ""}</div>
    ${body}
  </section>`;
}

function renderBulletBox(title, values, emptyText = "未单独列出") {
  const items = uniqueStrings(values);
  return `<div class="info-box"><h4>${escapeHTML(title)}</h4>
    ${items.length ? `<ul class="clean-list">${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`
      : `<div class="empty-note">${escapeHTML(emptyText)}</div>`}
  </div>`;
}

function renderDefinitionCard(concept) {
  const definition = concept.definition || {};
  const statement = definition.statement || "";
  if (!statement) return "";
  const coreIdeas = uniqueStrings(concept.core_ideas).filter(
    (idea) => normalize(idea) !== normalize(statement)
  );
  const examples = uniqueStrings(concept.examples);
  const nonExamples = uniqueStrings(concept.non_examples);
  const boundaryBoxes = [
    renderBulletBox("成立条件", definition.conditions),
    renderBulletBox("例外", definition.exceptions),
    renderBulletBox("边界提醒", definition.boundary_notes),
  ].join("");

  const exampleBlock = examples.length || nonExamples.length
    ? `<div class="subsection"><div class="eyebrow-small">正例与反例</div>
      <div class="two-col">
        ${renderBulletBox("正例", examples, "当前未拆分出正例")}
        ${renderBulletBox("错误认识 / 反例", nonExamples, "当前未拆分出反例")}
      </div></div>`
    : "";

  const body = `<p class="statement">${escapeHTML(statement)}</p>
    ${definition.scope ? `<div class="scope-box"><b>适用范围：</b>${escapeHTML(definition.scope)}</div>` : ""}
    ${coreIdeas.length ? `<div class="subsection"><div class="eyebrow-small">核心要点</div>
      <ul class="clean-list">${coreIdeas.map((idea) => `<li>${escapeHTML(idea)}</li>`).join("")}</ul></div>` : ""}
    <div class="subsection"><div class="eyebrow-small">条件与边界</div>
      <div class="three-col">${boundaryBoxes}</div></div>
    ${exampleBlock}`;

  return renderCard("sec-core", "定", "核心定义", body, "chem-concept-v1");
}

function renderFormulaCard(formulas) {
  const body = `<p class="empty-note">下列化学式只表示“在该概念的教材摘要或规范化讲解中出现过”，不自动等于概念的中心物质。</p>
    <div class="formula-grid">${formulas.map((formula) => `
      <article class="formula-card">
        <div class="formula-symbol">${escapeHTML(formula.display_formula || formula.formula)}</div>
        <div class="formula-meta">
          <span class="chip">${escapeHTML(label(LABELS.formulaKind, formula.formula_kind))}</span>
          <span class="chip brand">${escapeHTML(label(LABELS.formulaRole, formula.role))}</span>
          ${formula.review_method === "curated_formula_context" ? '<span class="chip info">规则修订</span>' : ""}
        </div>
        <p class="formula-note">${escapeHTML(formula.note || "")}</p>
      </article>`).join("")}</div>`;
  return renderCard("sec-formulas", "式", "化学式与表示", body, `${formulas.length} 条审核记录`);
}

function renderEquationCard(equations, extraction, teacher) {
  const groups = groupBy(equations, (equation) => equation.review_set_key);
  const extractionBlock = extraction ? `<div class="note-block warning">
    <b>方程抽取复核：</b>${escapeHTML(label(LABELS.extractionOutcome, extraction.outcome))}
    · ${escapeHTML(String(extraction.classification).replaceAll("_", " "))}<br>
    ${escapeHTML(extraction.resolution || "")}
  </div>` : "";

  const body = `${extractionBlock}
    ${groups.size ? [...groups.values()].map((records) => renderEquationGroup(records, teacher)).join("")
      : '<div class="empty-note">该概念已完成方程抽取复核，但没有需要保留的反应方程。</div>'}`;
  return renderCard("sec-equations", "反", "反应方程", body, `${equations.length} 条审核记录`);
}

function renderEquationGroup(records, teacher) {
  const first = records[0];
  const methods = [...new Set(records.map((record) => record.review_method))];
  const conditions = uniqueStrings(first.conditions);
  const setNotes = uniqueStrings(first.set_notes);
  const ambiguities = uniqueStrings(first.ambiguity_notes);
  const pages = uniqueStrings(
    records.flatMap((record) => safeArray(record.source_refs).map((ref) => pagesText(ref.pages)))
  );
  return `<article class="equation-group">
    <div class="equation-head">
      <h4>${escapeHTML(first.review_set_title)}</h4>
      <span class="chip info">${escapeHTML(label(LABELS.equationDomain, first.domain))}</span>
      ${methods.map((method) => `<span class="chip">${escapeHTML(label(LABELS.equationMethod, method))}</span>`).join("")}
    </div>
    <div class="condition-list">
      <span>介质：${escapeHTML(String(first.medium || "未标注").replaceAll("_", " "))}</span>
      ${conditions.map((condition) => `<span>${escapeHTML(condition)}</span>`).join("")}
      ${pages.map((page) => `<span>${escapeHTML(page)}</span>`).join("")}
    </div>
    ${records.map((record) => `<div class="equation-item">
      <p class="equation-display">${escapeHTML(record.display)}</p>
      <div class="formula-meta">
        <span class="chip">${escapeHTML(String(record.role || "未标注").replaceAll("_", " "))}</span>
        <span class="chip ${record.review_method === "structural_review" ? "warn" : "ok"}">
          ${escapeHTML(label(LABELS.equationMethod, record.review_method))}
        </span>
      </div>
      ${record.note ? `<p class="equation-note">${escapeHTML(record.note)}</p>` : ""}
      ${teacher ? `<details class="details-box"><summary>机器校验与原始记录</summary>
        <div class="mono">${escapeHTML(record.review_id)}<br>${escapeHTML(record.machine_expression || "结构审查，无单一计量配平式")}</div>
      </details>` : ""}
    </div>`).join("")}
    ${setNotes.length ? `<div class="note-block"><b>情境说明：</b>${setNotes.map(escapeHTML).join("；")}</div>` : ""}
    ${ambiguities.length ? `<div class="note-block warning"><b>歧义提醒：</b>${ambiguities.map(escapeHTML).join("；")}</div>` : ""}
    <div class="note-block warning">条件与状态符号仅为元数据；机器校验不认证反应事实、机理或教材写法。</div>
  </article>`;
}

function renderTeachingCard(concept) {
  const teaching = concept.teaching || {};
  const sequence = uniqueStrings(teaching.teaching_sequence);
  const teacherNotes = uniqueStrings(teaching.teacher_notes);
  const analogy = teaching.analogy || {};
  const teacher = state.mode === "teacher";
  const body = `${teaching.student_explanation ? `<p class="statement">${escapeHTML(teaching.student_explanation)}</p>` : ""}
    ${sequence.length ? `<div class="subsection"><div class="eyebrow-small">建议学习顺序</div>
      <ol class="sequence">${sequence.map((step) => `<li>${escapeHTML(step)}</li>`).join("")}</ol></div>` : ""}
    ${analogy.text ? `<div class="subsection"><div class="eyebrow-small">教学类比</div>
      <div class="analogy">${escapeHTML(analogy.text)}
        ${analogy.limitations ? `<div class="limit"><b>类比边界：</b>${escapeHTML(analogy.limitations)}</div>` : ""}
      </div></div>` : ""}
    ${teacher && teacherNotes.length ? `<div class="subsection"><div class="eyebrow-small">教师备课提示</div>
      <ol class="sequence">${teacherNotes.map((note) => `<li>${escapeHTML(note)}</li>`).join("")}</ol></div>` : ""}`;
  return body ? renderCard("sec-teaching", "教", "教学讲解", body, teacher ? "教师视角" : "学生视角") : "";
}

function renderMisconceptionCard(concept) {
  const items = safeArray(concept.misconceptions);
  const body = `<div class="misconception-list">${items.map((item) => `
    <div class="misconception">
      <span class="mark">×</span>
      <div><div class="wrong">${escapeHTML(item.statement)}</div>
        <div class="right">${escapeHTML(item.correction)}</div></div>
    </div>`).join("")}</div>`;
  return renderCard("sec-misconceptions", "辨", "易错辨析", body, `${items.length} 条`);
}

function renderAssessmentCard(concept) {
  const assessment = concept.assessment || {};
  const types = uniqueStrings(assessment.common_question_types);
  const traps = uniqueStrings(assessment.typical_traps);
  const hints = uniqueStrings(assessment.practice_generation_hints);
  const teacher = state.mode === "teacher";
  const body = `<div class="two-col">
      ${renderBulletBox("常见题型", types)}
      ${renderBulletBox("典型陷阱", traps)}
    </div>
    ${teacher && hints.length ? `<div class="subsection"><div class="eyebrow-small">命题提示（不是标准题或答案）</div>
      <ul class="clean-list">${hints.map((hint) => `<li>${escapeHTML(hint)}</li>`).join("")}</ul></div>` : ""}
    ${assessment.difficulty ? `<div class="subsection"><span class="chip">建议难度：${escapeHTML(label(LABELS.difficulty, assessment.difficulty))}</span></div>` : ""}`;
  return renderCard("sec-assessment", "练", teacher ? "考法与命题" : "复习检查", body);
}

function renderConceptLink(conceptId, fallbackLabel) {
  const concept = state.conceptById.get(conceptId);
  const name = concept?.canonical_name || fallbackLabel || "未命名概念";
  return `<button class="concept-link" data-concept-id="${escapeHTML(conceptId)}">${escapeHTML(name)} →</button>`;
}

function renderRelationsCard(concept, relationRows, pairs) {
  const resolved = relationRows.filter((row) => row.resolution_status === "resolved" && row.target_concept_id);
  const gaps = relationRows.filter((row) => row.resolution_status !== "resolved");
  if (!resolved.length && !gaps.length && !pairs.length) return "";

  const byType = {
    prerequisites: new Map(),
    related: new Map(),
  };
  for (const row of resolved) {
    const map = byType[row.relation_type] || (byType[row.relation_type] = new Map());
    if (!map.has(row.target_concept_id)) {
      map.set(row.target_concept_id, row.target_label);
    }
  }

  const relationRowsHTML = Object.entries(byType).map(([type, map]) => {
    if (!map.size) return "";
    const typeLabel = type === "prerequisites" ? "前置知识" : "相关概念";
    return `<div class="relation-row"><span class="label">${typeLabel}</span>
      ${[...map.entries()].map(([id, fallback]) => renderConceptLink(id, fallback)).join("")}</div>`;
  }).join("");

  const seenGaps = new Set();
  const gapHTML = gaps.map((row) => {
    const key = `${row.target_label}|${row.resolution_status}`;
    if (seenGaps.has(key)) return "";
    seenGaps.add(key);
    const review = state.relationReviewByLabel.get(row.target_label);
    const disposition = review ? label(LABELS.relationDisposition, review.review_disposition) : "";
    const rationale = review?.review_rationale || row.resolution_note || "尚未找到唯一且语义等价的规范概念。";
    return `<div class="gap-row">
      <span class="gap-label">${escapeHTML(row.target_label)}
        <span class="gap-note">${escapeHTML(disposition)}${disposition ? " · " : ""}${escapeHTML(rationale)}</span>
      </span>
      <span class="chip ${row.resolution_status === "external_prior" ? "info" : "warn"}">
        ${escapeHTML(label(LABELS.relationStatus, row.resolution_status))}
      </span>
    </div>`;
  }).join("");

  const pairHTML = pairs.map((pair) => {
    const isLeft = pair.left_concept_id === concept.concept_id;
    const otherId = isLeft ? pair.right_concept_id : pair.left_concept_id;
    const otherName = isLeft ? pair.right_name : pair.left_name;
    return `<article class="pair-card">
      <div>${renderConceptLink(otherId, otherName)}</div>
      <div class="dimensions">${safeArray(pair.dimensions).map((item) => `<span>${escapeHTML(item)}</span>`).join("")}</div>
      <div>${escapeHTML(pair.distinction || "")}</div>
    </article>`;
  }).join("");

  const body = `${relationRowsHTML ? `<div class="relation-groups">${relationRowsHTML}</div>` : '<div class="empty-note">当前没有已解析的前置或关联边。</div>'}
    ${gapHTML ? `<div class="subsection"><div class="eyebrow-small">未解析关系与缺口</div>
      <div class="gap-list">${gapHTML}</div></div>` : ""}
    ${pairHTML ? `<div class="subsection"><div class="eyebrow-small">易混概念对照</div>
      <div class="pair-grid">${pairHTML}</div></div>` : ""}`;
  return renderCard("sec-relations", "联", "知识关系", body, `${resolved.length} 条已解析`);
}

function renderEvidenceCard(concept, occurrences, teacher) {
  const quality = concept.quality || {};
  const issues = safeArray(quality.issue_details);
  const corrections = uniqueStrings(quality.corrections);
  const occurrenceHTML = occurrences.map((occurrence) => {
    const refs = safeArray(occurrence.textbook_refs);
    return `<div class="occurrence">
      <div class="top"><b>${escapeHTML(occurrence.original_name || concept.canonical_name)}</b>
        <span class="chip">${escapeHTML(occurrence.review_status || "未标注")}</span>
        ${occurrence.confidence != null ? `<span class="chip">来源置信度 ${escapeHTML(occurrence.confidence)}</span>` : ""}
      </div>
      <div class="path">${refs.map((ref) => `${escapeHTML(ref.book_title || "")} / ${escapeHTML(ref.chapter || "")} / ${escapeHTML(ref.section || "")} / ${escapeHTML(pagesText(ref.pages))}`).join("<br>")}</div>
      <div class="meta">occurrence ${escapeHTML(occurrence.occurrence_id)} · AI 摘要页码，未核对印刷原文</div>
    </div>`;
  }).join("");

  const issueHTML = issues.length
    ? `<div class="issue-list">${issues.map((issue) => `<div class="issue ${escapeHTML(issue.severity || "review")}">
        <b>${escapeHTML(issue.code || "open_issue")}</b> · ${escapeHTML(issue.message || "")}
      </div>`).join("")}</div>`
    : '<div class="empty-note">当前没有显式开放问题；这不等于专家已确认。</div>';

  const body = `<div class="three-col">
      <div class="info-box"><h4>审核状态</h4>${escapeHTML(quality.review_status || "未标注")}</div>
      <div class="info-box"><h4>人工签字</h4>${quality.human_verified ? "已确认" : "未确认"}</div>
      <div class="info-box"><h4>教材元数据</h4>出版社 / 版次 / ISBN / 原文均未核验</div>
    </div>
    <div class="subsection"><div class="eyebrow-small">教材出现记录</div>
      <div class="occurrence-list">${occurrenceHTML || '<div class="empty-note">没有 occurrence。</div>'}</div></div>
    <div class="subsection"><div class="eyebrow-small">开放问题与证据缺口</div>${issueHTML}</div>
    ${corrections.length ? `<div class="subsection"><div class="eyebrow-small">已应用的内容修订</div>
      <ul class="clean-list">${corrections.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul></div>` : ""}
    ${teacher ? `<details class="details-box"><summary>查看内部标识</summary>
      <div class="mono">concept ${escapeHTML(concept.concept_id)}<br>fingerprint ${escapeHTML(concept.provenance?.source_fingerprint || "")}</div>
    </details>` : ""}
    <div class="note-block warning">可用这张卡片做人工核验；在生产系统中应回填版权页、版次、ISBN、印刷页码和原文引文后才能升级为已核验证据。</div>`;
  return renderCard("sec-evidence", "证", "来源与审核证据", body, "未人工审定");
}

function renderPager(conceptId) {
  const index = state.viewEntries.findIndex((entry) => entry.concept.concept_id === conceptId);
  if (index < 0) return "";
  const previous = index > 0 ? state.viewEntries[index - 1].concept : null;
  const next = index < state.viewEntries.length - 1 ? state.viewEntries[index + 1].concept : null;
  return `<nav class="pager">
    <button ${previous ? `data-nav-concept="${escapeHTML(previous.concept_id)}"` : "disabled"}>
      <small>上一个概念</small><span>${escapeHTML(previous?.canonical_name || "—")}</span>
    </button>
    <button ${next ? `data-nav-concept="${escapeHTML(next.concept_id)}"` : "disabled"}>
      <small>下一个概念</small><span>${escapeHTML(next?.canonical_name || "—")}</span>
    </button>
  </nav>`;
}

function toggleKnown(conceptId) {
  if (state.known.has(conceptId)) state.known.delete(conceptId);
  else state.known.add(conceptId);
  writeStorage(STORAGE.known, [...state.known]);
  const button = $('[data-action="toggle-known"]');
  if (button) {
    const known = state.known.has(conceptId);
    button.classList.toggle("known", known);
    button.textContent = known ? "✓ 已标记学习" : "标记为已学习";
  }
  renderTree();
  renderSidebarStats();
}

async function copyCurrentLink() {
  const text = location.href;
  try {
    await navigator.clipboard.writeText(text);
    toast("链接已复制");
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    toast("链接已复制");
  }
}

boot();
