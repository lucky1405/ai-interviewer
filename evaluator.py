import json
import sqlite3
from fastapi import HTTPException
from pydantic import BaseModel
from config import get_llm_client
from database import DB_PATH

class SummaryRequest(BaseModel) :
    provider : str = "groq"
    api_key : str = ""

async def generate_recruiter_summary(interview_id : str, req : SummaryRequest) :
    with sqlite3.connect (DB_PATH) as conn :
        inter = conn.execute(
            "SELECT candidate_name, target_role, resume_text, selected_questions, status, overall_score, hiring_decision, recruiter_summary FROM interviews WHERE id = ?",
            (interview_id,)
        ).fetchone()
        
        if not inter:
            raise HTTPException(status_code=404, detail="Interview not found")

        msgs = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE interview_id = ? ORDER BY created_at ASC",
            (interview_id,)
        ).fetchall()

    candidate_name, target_role, resume_text, selected_q_json, status, score, decision, saved_summary = inter
    transcript = [{"role": m[0], "content": m[1], "created_at": m[2]} for m in msgs]

    if len(transcript) < 2:
        empty_summary = {
            "overall_score": 0,
            "hiring_decision": "Did Not Attend",
            "executive_summary": "The candidate initiated the session but no interview conversation took place. The transcript is completely empty.",
            "skill_breakdown": {
                "technical_depth": 0,
                "resume_authenticity": 0,
                "communication_clarity": 0,
                "problem_solving_on_followups": 0
            },
            "key_strengths": [],
            "areas_for_concern": ["Candidate abandoned the interview before answering questions."],
            "question_by_question_notes": []
        }
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE interviews SET status = 'COMPLETED', overall_score = 0, hiring_decision = 'Did Not Attend', recruiter_summary = ? WHERE id = ?",
                (json.dumps(empty_summary), interview_id)
            )
            
        return {
            "candidate_name": candidate_name,
            "target_role": target_role,
            "overall_score": 0,
            "hiring_decision": "Did Not Attend",
            "summary": empty_summary,
            "transcript": transcript
        }

    if status == "COMPLETED" and saved_summary != "{}" :
        return {
        "candidate_name": candidate_name,
        "target_role": target_role,
        "overall_score": score,
        "hiring_decision": decision,
        "summary": json.loads(saved_summary),
        "transcript": transcript
    }

    formatted_tx = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in transcript])
    client, cfg = get_llm_client(req.provider, req.api_key)
    eval_prompt = f"""
You are a Principal Engineering Hiring Manager writing a structured post-interview evaluation report.
Analyze the candidate's resume, the pre-selected questions, and the verbatim interview transcript (including how well they handled follow-up questions).

CANDIDATE: {candidate_name} ({target_role})
SELECTED RESUME QUESTIONS: {selected_q_json}
INTERVIEW TRANSCRIPT:
{formatted_tx}

Return ONLY a valid JSON object with this exact schema:
{{
  "overall_score": <integer 1-100>,
  "hiring_decision": "<Strong Hire | Hire | Borderline | No Hire>",
  "executive_summary": "<3-4 sentence high-level summary explaining how the candidate performed>",
  "skill_breakdown": {{
    "technical_depth": <integer 1-10>,
    "resume_authenticity": <integer 1-10>,
    "communication_clarity": <integer 1-10>,
    "problem_solving_on_followups": <integer 1-10>
  }},
  "key_strengths": ["<strength 1>", "<strength 2>"],
  "areas_for_concern": ["<concern or gap 1>", "<concern or gap 2>"],
  "question_by_question_notes": [
    {{
      "topic": "<question category>",
      "verdict": "<Strong | Adequate | Weak>",
      "recruiter_note": "<how well the candidate answered the initial question and the follow-up probe>"
    }}
  ]
}}
"""
    try :
        resp = await client.chat.completions.create(
            model=cfg["chat_model"],
            messages=[{"role": "system", "content": "You are a JSON-only API. Output ONLY valid JSON, without any markdown formatting, backticks, or text before/after."},
                      {"role" : "user", "content" : eval_prompt}],
            # response_format={"type" : "json_object"},
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
                    
        summary_data = json.loads(raw_output.strip())
        # summary_data = json.loads(resp.choices[0].message.content)
    except Exception as e :
        raise HTTPException(status_code=500, detail=f"Failed to generate evaluation: {str(e)}")
    overall_score = int(summary_data.get("overall_score",75))
    hiring_decision = summary_data.get("hiring_decision","Hire")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE interviews SET status = 'COMPLETED', overall_score = ?, hiring_decision = ?, recruiter_summary = ? WHERE id = ?",
            (overall_score, hiring_decision, json.dumps(summary_data), interview_id)
    )
    return {
    "candidate_name": candidate_name,
    "target_role": target_role,
    "overall_score": overall_score,
    "hiring_decision": hiring_decision,
    "summary": summary_data,
    "transcript": transcript
    }  

def get_all_candidates():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, candidate_name, target_role, status, overall_score, hiring_decision, created_at FROM interviews ORDER BY created_at DESC"
        ).fetchall()
    return [
        {
            "id": r[0],
            "candidate_name": r[1],
            "target_role": r[2],
            "status": r[3],
            "overall_score": r[4],
            "hiring_decision": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]     