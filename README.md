# LINE Diet Tracking Bot

This repository contains a LINE chatbot designed to help users track their daily diet and exercise. 

I built this project as a hands-on learning experience for data engineering and pair-programming with agentic AI.  This project is assisted by Google DeepMind's Antigravity. Almost everything is a first-time experience for me. (Except, coding in python, and domain knowledge of health sciences.)

## Project Overview

The objective was to create a functional, persistent application for diet and exercise tracking.  Rather than a standalone data script, the bot processes natural language and images from users, extracting nutritional information and keeping a daily tally of calories and macronutrients.  The LINE BOT communicates in traditional Mandarin so that my parents can use it. 

Key functionalities include:
*   **Conversational Logging:** Parsing unstructured text (e.g., "I walked for 30 minutes and ate a burger") into structured database entries.
*   **Image Recognition:** Using Google's Gemini Vision API to parse nutritional labels from uploaded photos.
*   **TDEE Tracking:** Calculating personalized goal metrics based on the user's basal metabolic rate and physical profile.
*   **Stateless Deployment:** Transitioning from local development to a cloud-hosted environment.

## Technologies Used

Through the development of this bot, I gained practical experience with several industry-standard tools:
*   **Backend Framework:** FastAPI (Python)
*   **Language Models:** Google Gemini 1.5 Flash (via `google-genai` SDK)
*   **Database Management:** SQLAlchemy bridging local SQLite for development and remote PostgreSQL (Supabase) for production.
*   **Deployment:** Docker and Google Cloud Run for serverless tracking.

## Technical Learnings

My priority here was understanding modern deployment environments and API integrations:
1.  **Prompt Engineering:** Learning how to strictly constrain LLM outputs into predictable JSON arrays to interact safely with a backend database. (Note: The agentic AI may occationally use system prompt to bypass problem that could have been solved by a careful system design.)
2.  **Containerization:** Understanding how to write Dockerfiles and separate dependency logic to ensure the code behaves identically locally and on Google Cloud.
3.  **CI/CD Basics:** Setting up continuous deployment directly from a GitHub repository, handling environment variables securely without committing them to source control.
4.  **Routing Optimization:** Creating a multi-tier logic path so that simple UI requests bypass the LLM entirely, saving API calls and reducing latency. And most importantly, keep it fun and characterized. 

## Structure
*   `main.py`: The FastAPI application and webhook router.
*   `models.py` / `database.py`: SQLAlchemy schema and database connection logic.
*   `functions/`: Contains the Gemini API client, deterministic logic paths, and offline responses.

---
*Developed by Ian Lin.*
