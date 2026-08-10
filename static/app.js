const state = {
  questions: null,
  part1Answers: {},   // id -> {choice, justification}
  part2Answers: {},   // id -> Set(selected indices)
};

const el = (id) => document.getElementById(id);

function showSection(name) {
  document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
  el(`section-${name}`).classList.add("active");
  document.querySelectorAll(".progress .step").forEach((s) => {
    s.classList.toggle("active", s.dataset.step === name);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadQuestions() {
  const res = await fetch("/api/questions");
  state.questions = await res.json();
  renderPart1();
  renderPart2();
  renderEssayMeta();
}

function renderPart1() {
  const container = el("part1-list");
  container.innerHTML = "";
  state.questions.part1.forEach((item, i) => {
    state.part1Answers[item.id] = { choice: null, justification: "" };

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${i + 1}. ${item.statement}</h3>
      <div class="choice-row">
        <div class="choice-btn agree" data-id="${item.id}" data-choice="agree">✅ Согласен</div>
        <div class="choice-btn disagree" data-id="${item.id}" data-choice="disagree">❌ Не согласен</div>
      </div>
      <textarea rows="2" data-justify="${item.id}" placeholder="Краткое обоснование (1–2 предложения)"></textarea>
    `;
    container.appendChild(card);
  });

  container.querySelectorAll(".choice-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const choice = btn.dataset.choice;
      state.part1Answers[id].choice = choice;
      const card = btn.closest(".card");
      card.querySelectorAll(".choice-btn").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
    });
  });

  container.querySelectorAll("textarea[data-justify]").forEach((ta) => {
    ta.addEventListener("input", () => {
      state.part1Answers[ta.dataset.justify].justification = ta.value;
    });
  });
}

function renderPart2() {
  const container = el("part2-list");
  container.innerHTML = "";
  state.questions.part2.forEach((item, i) => {
    state.part2Answers[item.id] = new Set();

    const card = document.createElement("div");
    card.className = "card";
    const title = document.createElement("h3");
    title.textContent = `${i + 1}. ${item.question}`;
    card.appendChild(title);

    item.options.forEach((opt, optIdx) => {
      const row = document.createElement("div");
      row.className = "option-row";
      row.dataset.id = item.id;
      row.dataset.opt = optIdx;
      const inputType = item.multiple ? "checkbox" : "radio";
      row.innerHTML = `<input type="${inputType}" name="p2-${item.id}"> <span>${opt}</span>`;
      row.addEventListener("click", (e) => {
        if (e.target.tagName !== "INPUT") {
          const input = row.querySelector("input");
          input.checked = item.multiple ? !input.checked : true;
        }
        handleOptionClick(item, row, optIdx);
      });
      card.appendChild(row);
    });

    container.appendChild(card);
  });
}

function handleOptionClick(item, row, optIdx) {
  const set = state.part2Answers[item.id];
  const card = row.closest(".card");

  if (item.multiple) {
    const input = row.querySelector("input");
    if (input.checked) {
      set.add(optIdx);
      row.classList.add("selected");
    } else {
      set.delete(optIdx);
      row.classList.remove("selected");
    }
  } else {
    set.clear();
    set.add(optIdx);
    card.querySelectorAll(".option-row").forEach((r) => {
      r.classList.remove("selected");
      r.querySelector("input").checked = false;
    });
    row.classList.add("selected");
    row.querySelector("input").checked = true;
  }
}

function renderEssayMeta() {
  const essay = state.questions.essay;
  el("essay-topic").textContent = `Тема: «${essay.topic}»`;
  el("essay-structure").textContent = essay.structure;
  el("word-range").textContent = `${essay.min_words}–${essay.max_words}`;
}

function validatePart1() {
  for (const [id, ans] of Object.entries(state.part1Answers)) {
    if (!ans.choice) return `Выберите вариант для утверждения №${id}.`;
    if (!ans.justification.trim()) return `Добавьте обоснование для утверждения №${id}.`;
  }
  return null;
}

function validatePart2() {
  for (const [id, set] of Object.entries(state.part2Answers)) {
    if (set.size === 0) return `Выберите ответ на вопрос №${id}.`;
  }
  return null;
}

function alertError(msg) {
  alert(msg);
}

el("btn-start").addEventListener("click", () => {
  const name = el("full_name").value.trim();
  if (!name) {
    alertError("Пожалуйста, укажите ФИО.");
    return;
  }
  showSection("part1");
});

el("btn-part1-next").addEventListener("click", () => {
  const err = validatePart1();
  if (err) return alertError(err);
  showSection("part2");
});

el("btn-part2-next").addEventListener("click", () => {
  const err = validatePart2();
  if (err) return alertError(err);
  showSection("part3");
});

const essayTextarea = el("essay-text");
essayTextarea.addEventListener("input", () => {
  const words = essayTextarea.value.trim().split(/\s+/).filter(Boolean).length;
  el("word-count").textContent = words;
});

el("btn-submit").addEventListener("click", async () => {
  const essayText = essayTextarea.value.trim();
  if (!essayText) {
    alertError("Напишите текст эссе.");
    return;
  }

  const payload = {
    full_name: el("full_name").value.trim(),
    email: el("email").value.trim(),
    part1: Object.entries(state.part1Answers).map(([id, a]) => ({
      id: Number(id),
      choice: a.choice,
      justification: a.justification,
    })),
    part2: Object.entries(state.part2Answers).map(([id, set]) => ({
      id: Number(id),
      selected: Array.from(set),
    })),
    essay_text: essayText,
  };

  const btn = el("btn-submit");
  btn.disabled = true;
  const status = el("submit-status");
  status.className = "";
  status.textContent = "Отправляем и проверяем ответы, это может занять до минуты…";

  try {
    const res = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      status.className = "error";
      status.textContent = data.error || "Ошибка отправки.";
      btn.disabled = false;
      return;
    }

    renderResult(data);
    showSection("result");
  } catch (e) {
    status.className = "error";
    status.textContent = "Не удалось связаться с сервером. Проверьте соединение и попробуйте снова.";
    btn.disabled = false;
  }
});

function renderResult(data) {
  const box = el("result-box");
  box.innerHTML = "";

  if (data.save_warning) {
    const warn = document.createElement("div");
    warn.className = "error-banner";
    warn.textContent = data.save_warning;
    box.appendChild(warn);
  }

  box.insertAdjacentHTML("beforeend", `
    <div class="result-row"><span>Часть 1</span><span>${data.part1.total} / ${data.part1.max}</span></div>
    <div class="result-row"><span>Часть 2</span><span>${data.part2.total} / ${data.part2.max}</span></div>
    <div class="result-row"><span>Часть 3 (эссе)</span><span>${data.part3.total} / ${data.part3.max}</span></div>
    <div class="result-total">Итого: ${data.total} / ${data.max_total}</div>
    <div class="result-grade">${data.grade}</div>
  `);

  if (data.part3.comment) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = `Комментарий по эссе: ${data.part3.comment}`;
    box.appendChild(p);
  }
}

loadQuestions();
