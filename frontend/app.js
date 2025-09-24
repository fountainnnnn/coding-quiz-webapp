// Backend API (FastAPI running locally)
const BACKEND_BASE_URL =
  new URLSearchParams(location.search).get("api") || "http://localhost:8000";

document.addEventListener("DOMContentLoaded", () => {
  const setupCard = document.getElementById("setup-card");
  const startBtn = document.getElementById("start-btn");
  const topicSelect = document.getElementById("topic");
  const difficultySelect = document.getElementById("difficulty");

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

  // Load quiz (10 questions)
  async function loadQuiz(topic, difficulty) {
    loadingOverlay.classList.remove("hidden");
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/generate_questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, difficulty, n: 10 }),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "ok" || !Array.isArray(data.questions)) {
        throw new Error(data.detail || data.message || "Failed to load questions");
      }

      sessionId = data.session_id; // store session ID
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
    feedbackEl.classList.add("hidden");
    feedbackEl.textContent = "";
    codeBlock.classList.add("hidden");
    optionsDiv.innerHTML = "";
    dragZone.innerHTML = "";
    dragZone.classList.add("hidden");
    dragActions.classList.add("hidden");

    // Render question text
    questionText.textContent = q.question || "";

    // Code block
    if (q.code_with_blanks) {
      codeBlock.textContent = q.code_with_blanks;
      codeBlock.classList.remove("hidden");
    }

    // Render by type
    if (q.type === "mcq" && Array.isArray(q.options)) {
      q.options.forEach((opt) => {
        const btn = document.createElement("button");
        btn.className = "option-btn";
        btn.textContent = opt;
        btn.addEventListener("click", () => submitAnswer(opt));
        optionsDiv.appendChild(btn);
      });
    } else if (q.type === "fill_code") {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-control";
      input.placeholder = "Fill in the blank...";
      const submitBtn = document.createElement("button");
      submitBtn.className = "btn btn-primary mt-2";
      submitBtn.textContent = "Submit";
      submitBtn.addEventListener("click", () =>
        submitAnswer(input.value)
      );
      optionsDiv.appendChild(input);
      optionsDiv.appendChild(submitBtn);
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

      // bind submit order button
      submitOrderBtn.onclick = () => {
        const order = [...dragZone.querySelectorAll(".draggable")].map(
          (el) => el.textContent
        );
        submitAnswer(order);
      };
    }
  }

  // Drag & drop support
  function enableDragAndDrop() {
    let dragged = null;
    dragZone.querySelectorAll(".draggable").forEach((el) => {
      el.addEventListener("dragstart", () => {
        dragged = el;
        setTimeout(() => el.classList.add("hidden"), 0);
      });
      el.addEventListener("dragend", () => {
        dragged.classList.remove("hidden");
        dragged = null;
      });
    });
    dragZone.addEventListener("dragover", (e) => e.preventDefault());
    dragZone.addEventListener("drop", (e) => {
      e.preventDefault();
      if (dragged) {
        const target = e.target.closest(".draggable");
        if (target) {
          dragZone.insertBefore(dragged, target);
        } else {
          dragZone.appendChild(dragged);
        }
      }
    });
  }

  // Submit answer
  async function submitAnswer(ans) {
    const q = questions[currentIndex];
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/check_answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId, // always send session_id
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
        feedbackEl.classList.remove("hidden");
        feedbackEl.className = "feedback success";
        feedbackEl.textContent = `✅ Correct! ${data.explanation}`;
        setTimeout(() => {
          currentIndex++;
          showQuestion();
        }, 1500);
      } else {
        feedbackEl.classList.remove("hidden");
        feedbackEl.className = "feedback error";
        feedbackEl.textContent = `❌ Incorrect. Try again.`;
        // stay on same question
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
    scoreText.textContent = `You scored ${score} / ${questions.length}`;
  }

  // Events
  startBtn.addEventListener("click", () => {
    const topic = topicSelect.value;
    const difficulty = difficultySelect.value;
    loadQuiz(topic, difficulty);
  });

  restartBtn.addEventListener("click", () => {
    resultCard.classList.add("hidden");
    setupCard.classList.remove("hidden");
  });
});
