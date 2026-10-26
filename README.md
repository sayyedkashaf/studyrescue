# Study Rescue

Study Rescue is a web app that turns WhatsApp study-group chats into tracked assignments, exams, and submissions, then helps students plan around them.

## Architecture

1. Import a WhatsApp export and parse messages.
2. Extract candidate tasks from messages with an LLM, then validate them.
3. Resolve deadlines deterministically from message timestamps.
4. Review and manage tasks in the web UI.
5. Plan feasibility, risk, and study schedules from open tasks.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
pytest
```

## How to run the evaluation

```bash
python -m eval.run_eval --split dev
python -m eval.run_eval --split test --final
```

## How to export a WhatsApp chat

Export a chat from WhatsApp (Android or iOS) as a `.txt` file, then upload it through the imports page.

## What is and is not machine learning in this project

Only the overrun median and the Naive Bayes baseline are statistical. The LLM does extraction. All other logic, including date resolution, feasibility checks, risk levels, and planning, is deterministic rule-based code.
