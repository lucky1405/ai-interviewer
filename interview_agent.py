import json
import base64
import sqlite3
import tempfile
import os
import uuid
from datetime import datetime
from typing import List, Dict
from fastapi import WebSocket, WebSocketDisconnect
import edge_tts
from config import get_llm_client
from database import DB_PATH

def save_message(interview_id : str, role : str, content : str) :
    with sqlite3.connect(DB_PATH) as conn :
        conn.execute (
            "INSERT INTO messages (id, interview_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), interview_id, role, content, datetime.utcnow().isoformat())
        )

async def synthesize_speech_b64(text : str) -> str :
    communicate = edge_tts.Communicate(text, voice="en-US-AndrewMultilingualNeural", rate="+6%")
    audio_bytes = b""
    async for chunk in communicate.stream() :
        if chunk["type"] == "audio" :
            audio_bytes += chunk["data"]
    return base64.b64encode(audio_bytes).decode("utf-8")

async def run_interview_socket(websocket : WebSocket, interview_id : str) :
    await websocket.accept()
    with sqlite3.connect(DB_PATH) as conn :
        row = conn.execute(
            "SELECT candidate_name, target_role, resume_text, selected_questions FROM interviews WHERE id = ?",
            (interview_id,)
        ).fetchone()

    if not row :
        await websocket.close()
        return

    candidate_name, target_role, resume_text, selected_q_json = row
    questions = json.loads(selected_q_json)
    current_q_idx = 0
    follow_up_step = 0
    history: List[Dict[str,str]] = []

    try :
        while True :
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type")
            provider = payload.get("provider", "groq")
            api_key = payload.get("api_key", "")
            client, cfg = get_llm_client(provider,api_key)

            if msg_type == "start" :
                first_q = questions[0]["question_to_ask"]
                greeting = (
                    f"Hi {candidate_name}, welcome to your {target_role} interview. "
                    f"I have reviewed your resume. Let's start with our first question: {first_q}"
                )
                history.append({"role" : "assistant", "content" : greeting})
                save_message(interview_id, "assistant", greeting)
                audio_b64 = await synthesize_speech_b64(greeting)
                await websocket.send_json({
                    "type": "ai_turn",
                    "text": greeting,
                    "audio_b64": audio_b64,
                    "progress": f"Question 1 of {len(questions)} (Main Question)",
                    "interview_complete": False
                })
                continue  
            user_text = ""
            if msg_type == "audio":
                audio_bytes = base64.b64decode(payload["audio_b64"])
                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name
                try:
                    if cfg["stt_model"]:
                        with open(tmp_path, "rb") as f:
                            tx = await client.audio.transcriptions.create(
                                file=("answer.webm", f.read()),
                                model=cfg["stt_model"],
                                language="en"
                            )
                        user_text = tx.text.strip()
                    else:
                        user_text = payload.get("fallback_text", "").strip()
                finally:
                    os.remove(tmp_path)
            elif msg_type == "text":
                user_text = payload.get("text", "").strip()

            if not user_text:
                await websocket.send_json({"type": "error", "message": "Could not hear audio clearly."})
                continue

            history.append({"role": "user", "content": user_text})
            save_message(interview_id, "user", user_text)
            await websocket.send_json({"type": "user_turn", "text": user_text})    

            user_lower = user_text.lower()
            repeat_keywords = ["repeat", "pardon", "say that again", "what was the", "did not catch", "can you repeat the question"]

            if any(w in user_lower for w in repeat_keywords) :
                current_q = questions[current_q_idx]["question_to_ask"]
                directive = f"The candidate wants to hear the question again. You MUST reply by saying exactly this: 'Sure, I can repeat that. {current_q}'"
                interview_complete = False
                progress_label = f"Repeating Question {current_q_idx + 1}"
            else :
                interview_complete = False
                if follow_up_step == 0 :
                    follow_up_step = 1
                    current_q = questions[current_q_idx]
                    directive = (
                        f"The candidate just answered Question #{current_q_idx + 1} ({current_q['category']}). "
                        f"Expected signal: {current_q['expected_signal']}. "
                        "Acknowledge their answer briefly in 1 sentence, then ask ONE concrete, probing follow-up question "
                        "drilling into a technical detail or edge case from what they just said. Keep total output under 40 words."
                    )
                    progress_label = f"Question {current_q_idx + 1} of {len(questions)} (Follow-Up Probe)"
                else :
                    follow_up_step = 0
                    current_q_idx = current_q_idx + 1

                    if current_q_idx < len(questions):
                        next_q = questions[current_q_idx]["question_to_ask"]
                        directive = (
                            "Briefly thank the candidate in 1 sentence, "
                            f"and then ask this exact next pre-selected resume question: '{next_q}'."
                        )
                        progress_label = f"Question {current_q_idx + 1} of {len(questions)} (Main Question)"
                    else:
                        interview_complete = True
                        directive = (
                            f"The candidate has completed all {len(questions)} questions. "
                            "Thank them warmly in 2 sentences and let them know their evaluation report is ready."
                        )
                        progress_label = "Interview Complete" 

            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are an AI Technical Interviewer evaluating {candidate_name} for {target_role}. "
                        f"Current instruction: {directive} "
                        "CRITICAL: Keep your spoken response brief, under 30 words. Speak in short, conversational sentences."
                    )
                }
            ] + history[-6:]

            completion = await client.chat.completions.create(
                model=cfg["chat_model"],
                messages=llm_messages,
                temperature=0.5,
                max_tokens=140,
            )
            ai_reply = completion.choices[0].message.content.strip()
            if not ai_reply :
                fallback_q = questions[current_q_idx]["question_to_ask"]
                ai_reply = f"Let me repeat that for you. {fallback_q}"

            history.append({"role": "assistant", "content": ai_reply})
            save_message(interview_id, "assistant", ai_reply)

            audio_b64 = await synthesize_speech_b64(ai_reply)
            await websocket.send_json({
                "type": "ai_turn",
                "text": ai_reply,
                "audio_b64": audio_b64,
                "progress": progress_label,
                "interview_complete": interview_complete
            })

    except WebSocketDisconnect:
        pass          