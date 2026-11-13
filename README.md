# AI Mock Interviewer

AI-powered mock interview tool: upload your resume + job description,
get tailored interview questions, answer them, and receive rubric-based
scores and feedback. Progress is saved across sessions.

## Features
- Tailored questions generated from resume + job description
- Rubric scoring (relevance, technical accuracy, clarity, depth)
- Session history stored in SQLite, progress and weakest-question tracking
- Retry with exponential backoff and model fallback for API reliability

## Architecture
Streamlit UI  --HTTP-->  FastAPI backend  -->  Gemini API
                                |
                             SQLite

## Tech Stack
FastAPI, Pydantic, SQLite, Streamlit, Google Gemini (google-genai)

## Run locally
1. `pip install -r requirements.txt`
2. Create `.env` with `GEMINI_API_KEY=your_key`
3. Backend: `uvicorn main:app --reload`
4. UI (new terminal): `streamlit run ui.py`

## API Endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| POST | /sessions | Create interview session |
| POST | /sessions/{id}/answer | Submit and evaluate an answer |
| GET | /sessions/{id} | Session progress |
| GET | /sessions | List past sessions |

## What I learned

This was my first project where I built a proper backend instead of just a
script, and it taught me a lot more than I expected.

I started with zero idea of what a REST API was. Now I understand how a client
sends a request, how the server validates it with Pydantic, and why things like
status codes (404, 400, 502) actually matter. I also learned that HTTP doesn't
remember anything between requests, which is why I needed session IDs and a
SQLite database to save interviews and scores.

The biggest lesson came from things breaking. Gemini models got renamed and
deprecated while I was building, I got 404s for model names and 503 "model is
busy" errors. Instead of just waiting, I added retries with exponential
backoff and a fallback to a second model, so the app doesn't depend on a single
model being available. I also moved settings like the model names and API URL
into environment variables so I don't have to touch the code to change them.

I also keep the AI part and the logic part separate: Gemini gives the judgment
(scores and feedback for each criterion), but the overall score is calculated
in my own Python code, because that part should be deterministic.

Next, I want to add OCR for scanned resumes and move the database to something
that persists on free hosting.
