from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.herald_agent import app as herald_app
from agents.sawt_agent import app as sawt_app

app = FastAPI(title="NEXUS Unified Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/herald", herald_app)
app.mount("/sawt", sawt_app)

@app.get("/health")
def health():
    return {"status": "online", "gateway": "unified"}