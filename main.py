import json
import os
import uuid
import db
import time

from google import genai
from google.genai import types
from google.genai import errors
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key,http_options=types.HttpOptions(timeout=60_000),
)
MODEL_NAMES = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
MAX_RETRIES = 3
app = FastAPI()

db.init_db()

# ---------- Request / Response models ----------
class InterviewRequest(BaseModel):
    resume_text: str
    job_description: str
    num_questions: int = 5


class EvaluationRequest(BaseModel):
    question: str
    answer: str
    job_description: str


class CriterionScore(BaseModel):
    score: int
    comment: str


class EvaluationResponse(BaseModel):
    relevance: CriterionScore
    technical_accuracy: CriterionScore
    clarity: CriterionScore
    depth: CriterionScore
    overall_score: float
    strengths: list[str]
    improvements: list[str]


class AnswerSubmit(BaseModel):
    question_index: int
    answer: str


# ---------- Prompt builders ----------
def build_prompt(resume_text: str, job_description: str, num_questions: int) -> str:
    return f"""You are an experienced technical interviewer.
Based on the candidate's resume and the job description below, generate
{num_questions} interview questions tailored to this candidate and role.

Return ONLY JSON in this format:
{{"questions": [{{"question": "...", "topic": "..."}}]}}

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}
"""


def build_evaluation_prompt(question: str, answer: str, job_description: str) -> str:
    return f"""You are a strict but fair technical interviewer.
Evaluate the candidate's answer using this rubric. Score each criterion from 1 to 10.

- relevance: does the answer actually address the question?
- technical_accuracy: is the content correct and specific?
- clarity: is it well structured and easy to follow?
- depth: does it go beyond surface level with examples or reasoning?

Return ONLY JSON in exactly this format:
{{
  "relevance": {{"score": 0, "comment": "..."}},
  "technical_accuracy": {{"score": 0, "comment": "..."}},
  "clarity": {{"score": 0, "comment": "..."}},
  "depth": {{"score": 0, "comment": "..."}},
  "strengths": ["..."],
  "improvements": ["..."]
}}

JOB DESCRIPTION:
{job_description}

QUESTION:
{question}

CANDIDATE'S ANSWER:
{answer}
"""


# ---------- Helper functions ----------
def ask_gemini_json(prompt: str) -> dict:
    for model_name in MODEL_NAMES:
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
                return json.loads(response.text)
            except json.JSONDecodeError:
                raise HTTPException(status_code=502, detail="AI returned invalid JSON")
            except errors.ServerError as e:
                print(f"[{model_name}] server error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(2**attempt)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Gemini call failed: {e}")
        print(f"[{model_name}] failed, switching to next model")

    raise HTTPException(
        status_code=503,
        detail="All models failed after multiple attempts. Please try again later.",
    )

def evaluate(question: str, answer: str, job_description: str) -> dict:
    data = ask_gemini_json(build_evaluation_prompt(question, answer, job_description))
    try:
        scores = [
            data[key]["score"]
            for key in ("relevance", "technical_accuracy", "clarity", "depth")
        ]
    except (KeyError, TypeError):
        raise HTTPException(status_code=502, detail="AI response missing rubric fields")
    data["overall_score"] = round(sum(scores) / len(scores), 1)
    return data

def get_session_or_404(session_id: str) -> dict:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session




# ---------- Endpoints ----------
@app.get("/")
def read_root():
    return {"message": "Hello, Manasvi's Interview Agent is running!"}


@app.post("/generate-questions")
def generate_questions(request: InterviewRequest):
    return ask_gemini_json(
        build_prompt(request.resume_text, request.job_description, request.num_questions)
    )


@app.post("/evaluate-answer", response_model=EvaluationResponse)
def evaluate_answer(request: EvaluationRequest):
    return evaluate(request.question, request.answer, request.job_description)


@app.post("/sessions")
def create_session(request: InterviewRequest):
    data = ask_gemini_json(
        build_prompt(request.resume_text, request.job_description, request.num_questions)
    )
    if "questions" not in data:
        raise HTTPException(status_code=502, detail="AI response missing questions")

       
    session_id = str(uuid.uuid4())
    db.create_session(session_id, request.job_description, data["questions"])
    return {"session_id": session_id, "questions": data["questions"]}

@app.post("/sessions/{session_id}/answer")
def submit_answer(session_id: str, body: AnswerSubmit):
    session = get_session_or_404(session_id)

    if not 0 <= body.question_index < len(session["questions"]):
        raise HTTPException(status_code=400, detail="Invalid question_index")

    question = session["questions"][body.question_index]["question"]
    evaluation = evaluate(question, body.answer, session["job_description"])

    db.save_answer(session_id, body.question_index, body.answer, evaluation)
    return {"question": question, "evaluation": evaluation}

@app.get("/sessions")
def list_sessions():
    return db.list_sessions()

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    session = get_session_or_404(session_id)
    answers = db.get_answers(session_id)
    scores = [a["evaluation"]["overall_score"] for a in answers.values()]

    # Find the question with the lowest overall score
    weakest_question = None
    lowest_score = None
    for index, item in answers.items():
        score = item["evaluation"]["overall_score"]
        if lowest_score is None or score < lowest_score:
            lowest_score = score
            weakest_question = session["questions"][index]["question"]

    return {
        "total_questions": len(session["questions"]),
        "answered": len(answers),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "weakest_question": weakest_question,
        "questions": session["questions"],
        "answers": answers,
    }