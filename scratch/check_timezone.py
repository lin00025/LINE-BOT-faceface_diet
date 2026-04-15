import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine, SessionLocal, Base
from models import UserProfile, LogEntry
from main import get_today_logs, get_today_summary
import datetime
import zoneinfo

def test_timezone():
    # Setup test DB
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # 1. Create Profile
    user_id = "test_user_tz"
    profile = db.query(UserProfile).filter_by(line_user_id=user_id).first()
    if not profile:
        profile = UserProfile(
            line_user_id=user_id,
            name="Test User",
            timezone="America/New_York",
            target_calories=2000
        )
        db.add(profile)
        db.commit()
    else:
        profile.timezone = "America/New_York"
        db.commit()

    # Clear logs
    db.query(LogEntry).filter_by(line_user_id=user_id).delete()
    db.commit()

    # Create logs
    # Assume right now is "now" in UTC
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    
    # Let's say user's timezone is New York
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    now_ny = now_utc.astimezone(ny_tz)
    
    # 1 log 1 hour ago
    log1 = LogEntry(line_user_id=user_id, record_type="FOOD", calories=500, description="Apple", timestamp=(now_utc - datetime.timedelta(hours=1)).replace(tzinfo=None))
    
    # 1 log 25 hours ago
    log2 = LogEntry(line_user_id=user_id, record_type="FOOD", calories=1000, description="Pizza", timestamp=(now_utc - datetime.timedelta(hours=25)).replace(tzinfo=None))
    
    db.add_all([log1, log2])
    db.commit()
    
    logs = get_today_logs(db, user_id, profile.timezone)
    print("Logs from today (NY):", len(logs))
    for log in logs:
        print(f" - {log.description} at {log.timestamp}")
        
    db.close()

if __name__ == "__main__":
    test_timezone()
