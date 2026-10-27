import os
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import init_db
from resume_parser import parse_resume_and_select_questions
from interview_agent import run_interview_socket
from evaluator import generate_recruiter_summary, get_all_candidates, SummaryRequest
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
init_db()

app = FastAPI(title="AI Resume Interviewer & Recruiter Portal")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/v1/upload-resume")
async def upload_resume_router(
    resume_file : UploadFile = File(...),
    target_role : str = Form("Software Engineer"),
    provider : str = Form("groq"),
    api_key : str = Form("")
) :
    return await parse_resume_and_select_questions(resume_file, target_role, provider, api_key)

@app.websocket("/ws/interview/{interview_id}")
async def interview_ws_route(websocket : WebSocket, interview_id : str) :
    return await run_interview_socket(websocket, interview_id)

@app.post("/api/v1/generate-summary/{interview_id}")
async def generate_summary_route(interview_id : str, req : SummaryRequest) :
    return await generate_recruiter_summary(interview_id, req)

@app.get("/api/v1/recruiter/candidates")
async def list_candidates_route() :
    return get_all_candidates()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")