# AI Interviewer

A real-time, full-stack voice AI application that conducts dynamic technical interviews tailored to a candidate's resume. 

Upload a PDF resume, and the AI will extract your technical background, generate personalized questions, conduct a live voice-to-voice interview over WebSockets, and provide a final hiring evaluation scorecard.

## ✨ Features
* **Resume Parsing:** Uses PyMuPDF and LLMs to dynamically select question topics based on candidate experience.
* **Real-Time Voice Engine:** Bi-directional audio streaming via WebSockets for ultra-low latency conversation.
* **Smart State Management:** Handles dynamic interruptions, requests to repeat questions, and follow-up probing.
* **Automated Evaluation:** Generates a final JSON-structured scorecard detailing strengths, weaknesses, and a hiring recommendation.

## 🛠️ Tech Stack
* **Backend:** FastAPI, Python, SQLite, WebSockets
* **AI & Audio Pipeline:** Groq API (Llama-3 / GPT-OSS), Whisper (STT), `edge-tts` (in-memory neural TTS)
* **Frontend:** Vanilla JavaScript, HTML5, CSS3, Web Audio API

## 🚀 Local Setup

**1. Clone the repository**
```bash
git clone [https://github.com/lucky1405/ai-interviewer.git](https://github.com/lucky1405/ai-interviewer.git)
cd ai-interviewer
```

**2. Install dependencies**
```bash
pip install fastapi "uvicorn[standard]" edge-tts pymupdf groq python-dotenv python-multipart
```

**3. Set up environment variables**
Create a .env file in the root directory and add your Groq API key
GROQ_API_KEY=your_api_key_here

**4. Run the application**
```bash
uvicorn main:app --reload
```