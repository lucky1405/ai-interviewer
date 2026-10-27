import json
import uuid
import sqlite3
from datetime import datetime
import fitz
from fastapi import UploadFile, HTTPException
from config import get_llm_client
from database import DB_PATH

PREDEFINED_QUESTION_BANK = [
    {"id": "Q1", "category": "Project Architecture", "template": "Walk me through the architecture of the most complex project on your resume and why you chose that tech stack."},
    {"id": "Q2", "category": "Debugging & Bottlenecks", "template": "Tell me about the hardest performance bottleneck, bug, or scaling issue you solved in one of your listed projects."},
    {"id": "Q3", "category": "Database & Data Modeling", "template": "How did you design the database schema or data pipeline in your project, and what trade-offs did you make?"},
    {"id": "Q4", "category": "API & System Integration", "template": "How did you handle error recovery, rate limits, or latency when integrating external APIs or microservices?"},
    {"id": "Q5", "category": "Testing & Production Readiness", "template": "If one of your resume projects suddenly received 100x traffic tomorrow, what would break first and how would you fix it?"},
    {"id": "Q6", "category": "AI & LLM Engineering", "template": "For your AI/ML work, how did you evaluate output quality, prevent hallucinations, or manage inference latency?"},
    {"id": "Q7", "category": "Teamwork & Trade-offs", "template": "Describe a technical disagreement or tight deadline you faced during your past experience and how you prioritized what to ship."}
]

async def parse_resume_and_select_questions(resume_file : UploadFile, target_role : str, provider : str, api_key : str) :
    pdf_bytes = await resume_file.read()
    try :
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        resume_text = "\n".join([page.get_text("text") for page in doc]).strip()
    except Exception as e :
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {str(e)}")

    if not resume_text :
        raise HTTPException(status_code=400, detail="Uploaded PDF contains no extractable text.")

    client, cfg = get_llm_client(provider, api_key)

    selector_prompt = f"""
    You are a technical recruiter preparing a structured interview.
    1. Extract the candidate's full name from the resume.
    2. From the PRE-DEFINED QUESTION BANK below, select the 3 best questions that match the candidate's resume skills and projects.
    3. Customize each selected question slightly so it explicitly mentions the specific project name or technology written on their resume.

    PRE-DEFINED QUESTION BANK:
    {json.dumps(PREDEFINED_QUESTION_BANK, indent=2)}

    CANDIDATE RESUME:
    {resume_text[:5000]}

    Return ONLY a valid JSON object matching this exact structure:
    {{
    "candidate_name": "Extracted Name",
    "selected_questions": [
        {{
         "id": "Q1",
        "category": "Project Architecture",
        "question_to_ask": "Customized question mentioning their specific project",
        "expected_signal": "What a strong technical answer should mention"
        }}
    ]
    }}
    """
    try : 
        resp = await client.chat.completions.create(
            model=cfg["chat_model"],
            messages=[{"role": "system", "content": "You are a JSON-only API. Output ONLY valid JSON, without any markdown formatting, backticks, or text before/after."},
                      {"role":"user", "content" : selector_prompt}],
            # response_format={"type":"json_object"},
            temperature=0.2,
        )
        raw_output = resp.choices[0].message.content.strip()
        
        #Add this block to safely strip the markdown backticks
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
            
        parsed_plan = json.loads(raw_output.strip())

    except Exception as e :
        raise HTTPException(status_code=500, detail=f"LLM parsing failed: {str(e)}")

    candidate_name = parsed_plan.get("candidate_name", "Candidate")
    selected_questions = parsed_plan.get("selected_questions", [])[:3]

    interview_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO interviews 
               (id, candidate_name, target_role, resume_text, selected_questions, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                interview_id,
                candidate_name,
                target_role,
                resume_text,
                json.dumps(selected_questions),
                "IN_PROGRESS",
                datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            )
        )

    return {
        "interview_id": interview_id,
        "candidate_name": candidate_name,
        "selected_questions": selected_questions
    }    