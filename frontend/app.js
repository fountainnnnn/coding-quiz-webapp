// Backend API (FastAPI running locally)
const BACKEND_BASE_URL =
  new URLSearchParams(location.search).get("api") || "http://localhost:8000";

document.addEventListener("DOMContentLoaded", () => {
  const setupCard = document.getElementById("setup-card");
  const startBtn = document.getElementById("start-btn");
  const topicSelect = document.getElementById("topic");
  const difficultySelect = document.getElementById("difficulty");
  const languageSelect = document.getElementById("language");
  const numQuestionsInput = document.getElementById("num-questions");

  const quizContainer = document.getElementById("quiz-container");
  const resultCard = document.getElementById("result-card");
  const questionText = document.getElementById("question-text");
  const codeBlock = document.getElementById("code-block");
  const optionsDiv = document.getElementById("options");
  const dragZone = document.getElementById("dragdrop-zone");
  const dragActions = document.getElementById("dragdrop-actions");
  const submitOrderBtn = document.getElementById("submit-order-btn");
  const feedbackEl = document.getElementById("feedback");
  const scoreText = document.getElementById("score-text");
  const restartBtn = document.getElementById("restart-btn");

  // Loading overlay
  const loadingOverlay = document.getElementById("loading-overlay");

  document.getElementById("year").textContent = new Date().getFullYear();

  let sessionId = null;
  let questions = [];
  let currentIndex = 0;
  let score = 0;
  let locked = false; // prevent multiple answers after correct

  // Load quiz
  async function loadQuiz(language, topic, difficulty, numQuestions) {
    loadingOverlay.classList.remove("hidden");
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/generate_questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          language,
          topic,
          difficulty,
          n: numQuestions,
        }),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "ok" || !Array.isArray(data.questions)) {
        throw new Error(data.detail || data.message || "Failed to load questions");
      }

      sessionId = data.session_id;
      questions = data.questions;
      currentIndex = 0;
      score = 0;

      setupCard.classList.add("hidden");
      quizContainer.classList.remove("hidden");
      showQuestion();
    } catch (err) {
      console.error("Quiz load error:", err);
      alert("Failed to load quiz. Please try again.");
    } finally {
      loadingOverlay.classList.add("hidden");
    }
  }

  // Render a question
  function showQuestion() {
    if (currentIndex >= questions.length) {
      return showResults();
    }

    const q = questions[currentIndex];

    // Reset UI
    locked = false; // reset lock per question
    feedbackEl.classList.add("hidden");
    feedbackEl.textContent = "";
    codeBlock.classList.add("hidden");
    optionsDiv.innerHTML = "";
    dragZone.innerHTML = "";
    dragZone.classList.add("hidden");
    dragActions.classList.add("hidden");

    // Render question text with numbering
    questionText.textContent = `Q${currentIndex + 1}/${questions.length}: ${q.question || ""}`;

    // Code block rendering
    if (q.type === "fill_code" && q.code_with_blanks) {
      const codeHTML = q.code_with_blanks.replace(/___/g, () => {
        return `<span class="blank" contenteditable="true" data-blank></span>`;
      });
      codeBlock.innerHTML = `<code>${codeHTML}</code>`;
      codeBlock.classList.remove("hidden");

      const submitBtn = document.createElement("button");
      submitBtn.className = "btn btn-primary mt-2";
      submitBtn.textContent = "Submit";
      submitBtn.addEventListener("click", () => {
        if (!locked) {
          const blanks = [...codeBlock.querySelectorAll("[data-blank]")].map(
            (el) => el.innerText.trim()
          );
          submitAnswer(blanks);
        }
      });
      optionsDiv.appendChild(submitBtn);

      // Auto-expand blanks
      codeBlock.querySelectorAll("[data-blank]").forEach((el) => {
        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submitBtn.click();
          }
        });

        const resize = () => {
          const span = document.createElement("span");
          span.style.visibility = "hidden";
          span.style.position = "absolute";
          span.style.whiteSpace = "pre";
          span.style.font = getComputedStyle(el).font;
          span.textContent = el.textContent || "___";
          document.body.appendChild(span);
          el.style.width = span.offsetWidth + 20 + "px";
          span.remove();
        };
        el.addEventListener("input", resize);
        resize();
      });
    } else if (q.type === "mcq" && Array.isArray(q.options)) {
      if (q.code_with_blanks) {
        codeBlock.textContent = q.code_with_blanks;
        codeBlock.classList.remove("hidden");
      }
      q.options.forEach((opt) => {
        const btn = document.createElement("button");
        btn.className = "option-btn";
        btn.textContent = opt;
        btn.addEventListener("click", () => {
          if (!locked) submitAnswer(opt, btn);
        });
        optionsDiv.appendChild(btn);
      });
    } else if (q.type === "drag_drop" && Array.isArray(q.options)) {
      dragZone.classList.remove("hidden");
      dragActions.classList.remove("hidden");

      q.options.forEach((opt) => {
        const el = document.createElement("div");
        el.className = "draggable";
        el.draggable = true;
        el.textContent = opt;
        dragZone.appendChild(el);
      });

      enableDragAndDrop();

      submitOrderBtn.onclick = () => {
        if (!locked) {
          const order = [...dragZone.querySelectorAll(".draggable")].map(
            (el) => el.textContent
          );
          submitAnswer(order);
        }
      };
    }
  }

  // Drag & drop support
  function enableDragAndDrop() {
    let dragged = null;
    let placeholder = document.createElement("div");
    placeholder.className = "drag-placeholder";

    function cleanupPlaceholder() {
      const existing = dragZone.querySelector(".drag-placeholder");
      if (existing) existing.remove();
    }

    dragZone.querySelectorAll(".draggable").forEach((el) => {
      el.addEventListener("dragstart", () => {
        dragged = el;
        setTimeout(() => el.classList.add("hidden"), 0);
      });
      el.addEventListener("dragend", () => {
        dragged.classList.remove("hidden");
        dragged = null;
        cleanupPlaceholder();
        dragZone.classList.remove("dragover");
      });
    });

    dragZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dragZone.classList.add("dragover");
      cleanupPlaceholder();

      const draggables = [...dragZone.querySelectorAll(".draggable:not(.hidden)")];
      let placed = false;

      for (const target of draggables) {
        const box = target.getBoundingClientRect();
        const offset = e.clientX - box.left;
        if (offset < box.width * 0.7) {
          dragZone.insertBefore(placeholder, target);
          placed = true;
          break;
        }
      }

      if (!placed) {
        dragZone.appendChild(placeholder);
      }
    });

    dragZone.addEventListener("dragleave", (e) => {
      if (!dragZone.contains(e.relatedTarget)) {
        dragZone.classList.remove("dragover");
        cleanupPlaceholder();
      }
    });

    dragZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dragZone.classList.remove("dragover");
      if (dragged) {
        if (placeholder.parentNode) {
          dragZone.insertBefore(dragged, placeholder);
        } else {
          dragZone.appendChild(dragged);
        }
      }
      cleanupPlaceholder();
    });
  }

  // Submit answer
  async function submitAnswer(ans, clickedBtn = null) {
    const q = questions[currentIndex];
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/check_answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          question_id: q.question_id,
          user_answer: ans,
        }),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "ok") {
        throw new Error(data.detail || data.message || "Failed to check answer");
      }

      const correct = data.correct;
      if (correct) {
        score++;
        locked = true; // 🔒 lock once correct
        if (clickedBtn) clickedBtn.classList.add("correct");
        feedbackEl.classList.remove("hidden");
        feedbackEl.className = "feedback success";
        feedbackEl.textContent = `✅ Correct! ${data.explanation}`;
        setTimeout(() => {
          currentIndex++;
          showQuestion();
        }, 1500);
      } else {
        if (clickedBtn) clickedBtn.classList.add("incorrect");
        feedbackEl.classList.remove("hidden");
        feedbackEl.className = "feedback error";
        feedbackEl.textContent = `❌ Incorrect. Try again.`;
      }
    } catch (err) {
      console.error("Answer submit error:", err);
      feedbackEl.classList.remove("hidden");
      feedbackEl.className = "feedback error";
      feedbackEl.textContent = `Error: ${err.message}`;
    }
  }

  // Results
  function showResults() {
    quizContainer.classList.add("hidden");
    resultCard.classList.remove("hidden");
    scoreText.textContent = `You scored ${score} out of ${questions.length} questions.`;
  }

  // Events
  startBtn.addEventListener("click", () => {
    const language = languageSelect.value;
    const topic = topicSelect.value;
    const difficulty = difficultySelect.value;
    const numQuestions = parseInt(numQuestionsInput.value, 10) || 10;

    loadQuiz(language, topic, difficulty, numQuestions);
  });

  restartBtn.addEventListener("click", () => {
    resultCard.classList.add("hidden");
    setupCard.classList.remove("hidden");
  });
});
