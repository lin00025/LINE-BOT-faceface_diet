import os
from dotenv import load_dotenv
from sqlalchemy import text, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR DEFAULT 'Asia/Taipei';"))
            print("Successfully added timezone column to Postgres!")
        except Exception as e:
            print(f"Error (might already exist): {e}")
else:
    print("DATABASE_URL not found in .env")
