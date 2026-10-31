import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import MAX_UPLOAD_MB
from .db import init_db, save, get
from .parser import parse_file
from .agents import analyze, design, resolve, change_requirement
from .llm import available


app = FastAPI(title="ArchIntel AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Approval(BaseModel):
    approved: bool = True
    resolutions: dict[str, str] = Field(default_factory=dict)


class Change(BaseModel):
    change_text: str
    approved: bool = False


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ollama_connected": available(),
        "database": "sqlite",
    }


@app.post("/api/analyze")
async def analyze_files(
    project_name: str = Form("ShopSphere"),
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one file.")

    docs = []
    for uploaded_file in files:
        data = await uploaded_file.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"{uploaded_file.filename} exceeds upload limit",
            )

        try:
            extracted_text = parse_file(uploaded_file.filename, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not extracted_text or not extracted_text.strip():
            raise HTTPException(
                status_code=400,
                detail=f"No readable text in {uploaded_file.filename}",
            )
        docs.append({"name": uploaded_file.filename, "text": extracted_text})

    project_id = str(uuid.uuid4())[:8]
    state = analyze(docs)
    state.update({
        "project_name": project_name,
        "documents": [
            {"name": doc["name"], "characters": len(doc["text"])}
            for doc in docs
        ],
        "status": "awaiting_approval" if state.get("conflicts") else "ready_for_design",
        "change_history": state.get("change_history", []),
        "human_decisions": state.get("human_decisions", []),
    })

    save(project_id, project_name, state)
    return {"project_id": project_id, "status": state["status"], "state": state}


@app.get("/api/projects/{pid}")
def project(pid: str):
    saved_project = get(pid)
    if not saved_project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project_id": pid,
        "name": saved_project["name"],
        "state": saved_project["state"],
    }


@app.post("/api/projects/{pid}/approve")
def approve(pid: str, req: Approval):
    saved_project = get(pid)
    if not saved_project:
        raise HTTPException(status_code=404, detail="Project not found")

    state = saved_project["state"]
    if not req.approved:
        state["status"] = "rejected_by_human"
    else:
        state = resolve(state, req.resolutions)
        unresolved_high = [
            item for item in state.get("conflicts", [])
            if item.get("severity") == "High" and item.get("status") == "unresolved"
        ]
        if unresolved_high:
            raise HTTPException(
                status_code=409,
                detail="Resolve every high-severity conflict first",
            )

        architecture, verification = design(state)
        state.update({
            "architecture": architecture,
            "verification": verification,
            "status": "verified" if verification.get("score", 0) >= 70 else "needs_review",
        })
        for step in state.get("plan", []):
            if step.get("step", 0) >= 3:
                step["status"] = "completed"

    save(pid, saved_project["name"], state)
    return {"project_id": pid, "status": state["status"], "state": state}


@app.post("/api/projects/{pid}/change")
def change(pid: str, req: Change):
    saved_project = get(pid)
    if not saved_project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not req.change_text.strip():
        raise HTTPException(status_code=400, detail="Change description is required")

    state = saved_project["state"]
    if not req.approved:
        state["status"] = "awaiting_human_approval"
        state["proposed_change"] = req.change_text
    else:
        old_architecture = state.get("architecture") or {}
        old_components = old_architecture.get("components", [])
        state["previous_architecture"] = old_architecture

        state = change_requirement(state, req.change_text)
        architecture, verification = design(state)
        state.update({
            "architecture": architecture,
            "verification": verification,
            "status": (
                "adapted_and_verified"
                if verification.get("score", 0) >= 70
                else "adapted_needs_review"
            ),
        })

        history = state.setdefault("change_history", [])
        latest_change = history[-1] if history else {}
        new_components = architecture.get("components", [])
        state["impact_summary"] = {
            "change": req.change_text,
            "affected_components": latest_change.get("affected_components", []),
            "verification_score": verification.get("score", 0),
            "old_component_count": len(old_components),
            "new_component_count": len(new_components),
        }

    save(pid, saved_project["name"], state)
    return {"project_id": pid, "status": state["status"], "state": state}
