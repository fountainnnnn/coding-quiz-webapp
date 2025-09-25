![License](https://img.shields.io/badge/license-Proprietary-red.svg)


# quiz-slides-generator
A generator that generates slides containing quizzes questions with questions, answers and explanations. Helps lecturers save time.


## Backend Setup

```bat
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```


To start backend run: <br>
`cd backend` <br>
`.\.venv\Scripts\activate` <br>
`python -m uvicorn src.app:app --host 0.0.0.0 --port 8000`

To start frontend run: <br>
`cd frontend`<br>
`python -m http.server 5173`