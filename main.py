from fastapi import FastAPI, Request, HTTPException
import os
from engineer_stats import run_engineer_stats

app = FastAPI()
API_KEY = os.getenv("API_KEY")

@app.get("/run")
def run(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        run_engineer_stats()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
