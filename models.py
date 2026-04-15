from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "users"
    
    line_user_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=True)
    
    # Demographic / Physiological Data (Current Snapshot)
    gender = Column(String, default="M")
    age = Column(Integer, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    body_fat_percentage = Column(Float, nullable=True)
    
    # Custom Goals
    target_protein_multiplier = Column(Float, default=1.0) 
    target_calories = Column(Integer, default=2000)
    
    # Location Preference
    timezone = Column(String, default="Asia/Taipei")
    
    # Tracks the exact time their core profile was last changed
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class LogEntry(Base):
    """
    An Event-based ledger. Every meal, exercise, or weight-in is a new row.
    """
    __tablename__ = "log_entries"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    line_user_id = Column(String, ForeignKey("users.line_user_id"))
    
    record_type = Column(String) # "FOOD", "EXERCISE", or "BODY_UPDATE"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow) 
    
    description = Column(String) 
    
    # Food/Exercise
    calories = Column(Float, default=0.0) 
    protein = Column(Float, default=0.0)
    fat = Column(Float, default=0.0)
    carbs = Column(Float, default=0.0)
    
    # Body Updates (for weight graph history)
    weight_kg = Column(Float, nullable=True)
    body_fat_percentage = Column(Float, nullable=True)
