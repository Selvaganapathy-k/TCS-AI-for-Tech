# ArchIntel AI — TCS Challenge 02

Agentic requirements-to-architecture MVP: multi-document extraction, conflict detection, planning, human approval, architecture generation, verification, and change adaptation.

## Stack
React/Vite · FastAPI · LangGraph · Ollama · MongoDB Atlas · PyMuPDF · python-docx · Mermaid

## Run
1. Install Ollama and run `ollama pull qwen2.5:3b` then `ollama serve`.
2. Backend:
   - `cd backend`
   - `python -m venv .venv`
   - Windows: `.venv\\Scripts\\activate`
   - `pip install -r requirements.txt`
   - Copy `.env.example` to `.env`
   - Set `MONGODB_URI` to your MongoDB Atlas connection string and enter the rotated password locally. URL-encode special characters in the password.
   - The API creates the `archintel` database and `projects` collection on startup. Change `MONGODB_DATABASE` if you want a different database name.
   - `uvicorn app.main:app --reload --port 8000`
3. Frontend:
   - `cd frontend`
   - `npm install`
   - `npm run dev`
4. Open http://localhost:5173.

## Use real project data
Upload requirements and supporting documents from your actual project. The API stores only analyses created from those uploads in MongoDB; it does not seed or fall back to sample data or a local SQLite database. Project names and change requests are entered by the user.

The LLM extracts and reasons over evidence. Python functions perform conflict checks, architecture mapping and verification. The LLM is not allowed to claim that a check passed: the verifier computes the result.

For a production release add authentication, upload scanning, tenant isolation, robust schema validation, full audit history, load tests, and a persistent vector index.
