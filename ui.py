import requests
import streamlit as st
import os
import pdfplumber

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
st.set_page_config(page_title="AI Mock Interviewer", page_icon="🎤")
st.title("🎤 AI Mock Interviewer")


def call_api(method: str, path: str, **kwargs):
    """Sends a request to the backend. Returns None and shows an error if it fails."""
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=90, **kwargs)
    except requests.exceptions.ConnectionError:
        st.error("Unable to connect to the backend. Is the FastAPI server running?")
        return None
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        st.error(f"Error {response.status_code}: {detail}")
        return None
    return response.json()

def extract_pdf_text(uploaded_file) -> str:
    with pdfplumber.open(uploaded_file) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()

#Streamlit reruns the script from top to bottom on every interaction, so we use session_state to keep track of the current interview session and its state.
if "session_id" not in st.session_state:
    st.session_state.session_id = None
    st.session_state.questions = []
    st.session_state.results = {}


# ---------- 1. Start a new interview ----------
st.subheader("1. Start a new interview")
uploaded_pdf = st.file_uploader("Upload resume (PDF)", type="pdf")
extracted_text = ""
if uploaded_pdf is not None:
    extracted_text = extract_pdf_text(uploaded_pdf)
    if not extracted_text:
        st.warning("PDF se text nahi nikla (scanned PDF ho sakta hai). Neeche text paste kar do.")

resume_text = st.text_area("Resume text", value=extracted_text, height=150)
job_description = st.text_area("Job description", height=150)
num_questions = st.number_input("Number of questions", min_value=1, max_value=10, value=5)

if st.button("Start Interview"):
    if not resume_text.strip() or not job_description.strip():
        st.warning("Fill in both resume and job description.")
    else:
        with st.spinner("Questions are being generated..."):
            data = call_api(
                "POST",
                "/sessions",
                json={
                    "resume_text": resume_text,
                    "job_description": job_description,
                    "num_questions": int(num_questions),
                },
            )
        if data:
            st.session_state.session_id = data["session_id"]
            st.session_state.questions = data["questions"]
            st.session_state.results = {}


# ---------- 2. Answer the questions ----------
if st.session_state.session_id:
    st.subheader("2. Answer the questions")

    for i, q in enumerate(st.session_state.questions):
        with st.expander(f"Q{i + 1}. {q['question']}", expanded=True):
            st.caption(f"Topic: {q.get('topic', 'General')}")
            answer = st.text_area("Your answer", key=f"answer_{i}")

            if st.button("Submit answer", key=f"submit_{i}"):
                if not answer.strip():
                    st.warning("Fill in your answer before submitting.")
                else:
                    with st.spinner("Answer is being evaluated..."):
                        data = call_api(
                            "POST",
                            f"/sessions/{st.session_state.session_id}/answer",
                            json={"question_index": i, "answer": answer},
                        )
                    if data:
                        st.session_state.results[i] = data["evaluation"]

            if i in st.session_state.results:
                ev = st.session_state.results[i]
                st.metric("Overall score", f"{ev['overall_score']}/10")

                criteria = ["relevance", "technical_accuracy", "clarity", "depth"]
                for col, key in zip(st.columns(len(criteria)), criteria):
                    col.metric(key.replace("_", " ").title(), ev[key]["score"])

                st.markdown("**Strengths**")
                st.markdown("\n".join(f"- {s}" for s in ev["strengths"]))
                st.markdown("**Improvements**")
                st.markdown("\n".join(f"- {s}" for s in ev["improvements"]))

    # ---------- 3. Progress ----------
    st.subheader("3. Progress")
    if st.button("Show progress"):
        summary = call_api("GET", f"/sessions/{st.session_state.session_id}")
        if summary:
            st.metric("Answered", f"{summary['answered']}/{summary['total_questions']}")
            if summary["average_score"] is not None:
                st.metric("Average score", f"{summary['average_score']}/10")
                st.write(f"**Weakest question:** {summary['weakest_question']}")


# ---------- Sidebar: past sessions ----------
#This is at the bottom of the file because Streamlit sidebar is rendered after the main content.
with st.sidebar:
    st.header("Past sessions")
    past = call_api("GET", "/sessions")
    if past:
        st.dataframe(past, hide_index=True)
    else:
        st.caption("No past sessions found.")