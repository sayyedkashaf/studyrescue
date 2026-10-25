import os
import sys
import random
import string
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import User, UserSettings, Task
from app.auth.security import hash_password

db = SessionLocal()
try:
    existing = db.query(User).filter(User.email == "demo@example.com").first()
    if existing:
        print("Demo user already exists.")
    else:
        password = os.environ.get("DEMO_PASSWORD")
        if not password:
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            print(password)
        user = User(email="demo@example.com", display_name="Demo Student", password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        settings = UserSettings(user_id=user.id)
        db.add(settings)
        db.commit()

        titles = [
            "Assignment 1",
            "Lab record",
            "Project report",
            "Quiz prep",
            "Exam revision",
            "Submission",
        ]
        for i, t in enumerate(titles):
            task = Task(
                user_id=user.id,
                title=f"[demo] {t}",
                kind="assignment",
                status="pending",
                deadline=date.today() + timedelta(days=i + 1),
                estimated_hours=2.0 + i,
            )
            db.add(task)
        db.commit()
finally:
    db.close()
