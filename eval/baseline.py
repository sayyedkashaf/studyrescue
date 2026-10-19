def keyword_predict(text: str) -> bool:
    lowered = text.lower()
    keywords = ["assignment", "submit", "submission", "deadline", "due", "exam", "test", "quiz", "last date", "project", "report", "lab", "record", "viva", "internal", "practical", "jama"]
    return any(k in lowered for k in keywords)
