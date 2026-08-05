cd backend
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000
cd frontend
npm run dev
cd ../