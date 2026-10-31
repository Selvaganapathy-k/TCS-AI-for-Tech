import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import MAX_UPLOAD_MB
from .db import close_db, get, init_db, ping_db, save
from .parser import parse_file
from .agents import analyze, design, resolve, change_requirement
from .llm import available

app=FastAPI(title="ArchIntel AI API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class Approval(BaseModel):
    approved:bool=True
    resolutions:dict[str,str]=Field(default_factory=dict)
class Change(BaseModel):
    change_text:str
    approved:bool=False

@app.on_event("startup")
def startup(): init_db()

@app.on_event("shutdown")
def shutdown(): close_db()

@app.get("/api/health")
def health():
    ping_db()
    return {"status":"ok","database_connected":True,"ollama_connected":available()}

@app.post("/api/analyze")
async def analyze_files(project_name:str=Form(...),files:list[UploadFile]=File(...)):
    project_name = project_name.strip()
    if not project_name:
        raise HTTPException(422,"Project name is required")
    docs=[]
    for f in files:
        data=await f.read()
        if len(data)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,f"{f.filename} exceeds upload limit")
        try: text=parse_file(f.filename,data)
        except ValueError as e: raise HTTPException(400,str(e))
        if not text.strip(): raise HTTPException(400,f"No readable text in {f.filename}")
        docs.append({"name":f.filename,"text":text})
    pid=str(uuid.uuid4())[:8]; state=analyze(docs)
    state.update({"project_name":project_name,"documents":[{"name":d["name"],"characters":len(d["text"])} for d in docs],
                  "status":"awaiting_approval" if state.get("conflicts") else "ready_for_design","change_history":[],"human_decisions":[]})
    save(pid,project_name,state)
    return {"project_id":pid,"status":state["status"],"state":state}

@app.get("/api/projects/{pid}")
def project(pid:str):
    p=get(pid)
    if not p: raise HTTPException(404,"Project not found")
    return {"project_id":pid,"name":p["name"],"state":p["state"]}

@app.post("/api/projects/{pid}/approve")
def approve(pid:str,req:Approval):
    p=get(pid)
    if not p: raise HTTPException(404,"Project not found")
    s=p["state"]
    if not req.approved: s["status"]="rejected_by_human"
    else:
        s=resolve(s,req.resolutions)
        blocked=[c for c in s.get("conflicts",[]) if c["severity"]=="High" and c["status"]=="unresolved"]
        if blocked: raise HTTPException(409,"Resolve every high-severity conflict first")
        a,v=design(s); s.update({"architecture":a,"verification":v,"status":"verified" if v["score"]>=70 else "needs_review"})
        for step in s["plan"]:
            if step["step"]>=3: step["status"]="completed"
    save(pid,p["name"],s)
    return {"project_id":pid,"status":s["status"],"state":s}

@app.post("/api/projects/{pid}/change")
def change(pid:str,req:Change):
    p=get(pid)
    if not p: raise HTTPException(404,"Project not found")
    s=p["state"]
    if not req.approved:
        s["status"]="awaiting_human_approval"; s["proposed_change"]=req.change_text
    else:
        old=s.get("architecture",{})
        s["previous_architecture"]=old
        s=change_requirement(s,req.change_text)
        a,v=design(s); s.update({"architecture":a,"verification":v,"status":"adapted_and_verified" if v["score"]>=70 else "adapted_needs_review"})
        s["impact_summary"]={"change":req.change_text,"affected_components":s["change_history"][-1]["affected_components"],"verification_score":v["score"],"old_component_count":len(old.get("components",[])),"new_component_count":len(a["components"])}
    save(pid,p["name"],s)
    return {"project_id":pid,"status":s["status"],"state":s}
