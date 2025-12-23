from fastapi import FastAPI
from agent.agent import run_agent

app = FastAPI()

@app.post("/analyze")
def analyze(symbol: str):
    return {"report": run_agent(symbol)}