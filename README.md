<!--- Agentic Crypto Researcher - README.md -->

![License](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-13+-black.svg)
![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg)

<br />

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Vercel-black?style=for-the-badge&logo=vercel)](https://agentic-crypto-researcher.vercel.app/)
[![API Docs](https://img.shields.io/badge/🤗_Hugging_Face-Backend_API-FFD21E?style=for-the-badge&logo=huggingface)](https://huggingface.co/spaces/jacobbista/agentic-crypto-researcher/tree/main)

# Agentic Crypto Researcher

Agentic Crypto Researcher is a full-stack AI application that autonomously researches, analyzes, and summarizes cryptocurrency market data using a visible agentic loop (Plan → Tools → Observations → Synthesis). It demonstrates a Tool-Augmented RAG pattern (retrieval via tools/APIs rather than a vector DB) and streams the agent’s reasoning to the UI.

## Key Features
- Quantitative analysis: fetches 30 days of price history from CoinGecko and computes RSI(14) and MACD(12,26,9).
- Qualitative research: fetches curated crypto news from CryptoPanic (Developer v2 API).
- Token profiling: retrieves token images and metadata from CoinGecko.
- Transparent agent loop: streams trace, tool usage, observations, and context events to the UI.
- Stateful memory: session-aware memory with rolling summaries when context grows.

## Architecture Overview

The backend is a FastAPI app exposing blocking and streaming research endpoints. The frontend is a Next.js app that connects to the backend and displays agent traces and streaming answers.

- agent/orchestrator.py — main agent loop and SSE emission
- agent/planner.py — classify intent and plan tool usage
- agent/tools.py — API wrappers (CoinGecko, CryptoPanic) and indicator math
- agent/memory.py — session memory handling and summarization
- agent/llm.py — OpenAI chat client wrapper

The agent loop:

1. Plan — classify the user query, extract symbols, detect language.
2. Retrieve (Tools) — call CoinGecko, CryptoPanic, or other APIs.
3. Augment — produce a compact JSON Context with tool results + memory.
4. Generate — LLM synthesizes the final answer, streamed as Markdown deltas.

## API Reference

Backend endpoints:

- `POST /research` — blocking JSON report.
- `POST /research/stream` — streams Server-Sent Events (SSE) with events: `trace`, `tool`, `observation`, `context`, `answer_delta`, `final`.

External APIs used:

- CoinGecko: price history (`/market_chart`), metadata, search.
- CryptoPanic (Developer v2): curated news and sentiment (`/posts`).

## Local Setup

Prerequisites

- Python 3.10+
- Node.js 18+
- OpenAI API key
- (Optional) CryptoPanic API key for news

1) Environment variables

Copy `env.example` to `.env` and set:

- `OPENAI_API_KEY=sk-...`
- `OPENAI_MODEL=gpt-4o-mini`
- `CRYPTOPANIC_API_KEY=...` (optional)
- `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`

2) Backend (FastAPI)

Create and activate a virtual environment, install dependencies, and run the server:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirement.txt
uvicorn api.main:app --reload --port 8000
```

3) Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

## Deployment

Backend (Hugging Face Space)

**Live URL:** [Access API](https://huggingface.co/spaces/jacobbista/agentic-crypto-researcher/tree/main)

The repo includes a Dockerfile for deployment to Hugging Face Spaces.

Steps:

1. Create a Docker Space on Hugging Face.
2. Set the following Secrets in the Space settings:
   - `OPENAI_API_KEY`
   - `CRYPTOPANIC_API_KEY` (optional)
   - `BACKEND_SHARED_SECRET` (strong random string for internal auth)
3. Push the Docker image / deploy. The Dockerfile exposes port 7860 by default.

Frontend (Vercel)

**Live URL:** [Launch App](https://agentic-crypto-researcher.vercel.app/)

1. Import the `frontend/` directory into Vercel.
2. Configure environment variables:
   - `BACKEND_URL`: your backend URL (e.g., a Hugging Face Space URL)
   - `BACKEND_SHARED_SECRET`: must match the backend secret
   - `APP_AUTH_TOKENS`: (optional) comma-separated tokens to gate the UI

Security pattern

This project implements a Shared Secret pattern. When `BACKEND_SHARED_SECRET` is set on both frontend and backend, the frontend sends an `X-Internal-Auth` header. The backend rejects requests missing this header to protect API usage and credits.

> **Note**: Access to the UI is gated via `APP_AUTH_TOKENS`. To request a temporary access token for testing purposes, please contact the development team.

## Example: Research Flow

1. User asks the agent to research `ETH`.
2. Planner identifies `ETH` and composes a tool plan.
3. Tools fetch price history + news.
4. Context is assembled and streamed to the LLM.
5. The backend streams `trace`, `tool`, and `answer_delta` SSE events to the UI.

## Files of Interest

- `api/` — FastAPI entrypoints
- `agent/` — planner, orchestrator, tools, memory, llm
- `frontend/` — Next.js UI and SSE client

## Contributing

Contributions welcome. Open an issue or PR with clear description and tests where applicable.

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0). 
**Non-commercial use only.** You may not use this material for commercial purposes without prior written permission from the developers.

## Disclaimer

This project is for research and educational purposes only and does not constitute financial advice. Cryptocurrency markets are volatile — do your own due diligence.

--
Built with ❤️ for transparent, agentic crypto research.
