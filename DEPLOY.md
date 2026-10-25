# Deploy (Render + Neon Postgres)

## Steps
1. Create a Postgres database on Neon and copy the connection string (use postgresql+psycopg://...).
2. Create a new Web Service on Render from this repo.
3. Set environment variables on Render:
   - ENV=production
   - SECRET_KEY=<random>
   - DATABASE_URL=<neon postgres url>
   - GEMINI_API_KEY=<your key>
   - GEMINI_MODEL=<model>
4. Build command: pip install -r requirements.txt
5. Start command: uvicorn app.main:app --host 0.0.0.0 --port 
6. Deploy. Run migrations/tables on startup via create_tables().
