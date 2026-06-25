import os
import json
import datetime
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("careerforge-mcp")

# Store profile and interview data locally in a data/ directory inside the project folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def ensure_data_dir():
    """Ensures that the local storage folder exists."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

@mcp.tool()
def read_student_profile(student_id: str) -> str:
    """Reads a student's profile information from local filesystem storage.

    Args:
        student_id: The unique alphanumeric ID of the student.
    """
    ensure_data_dir()
    profile_path = os.path.join(DATA_DIR, f"{student_id}_profile.json")
    if not os.path.exists(profile_path):
        # Return default blank profile if not exists
        default_profile = {
            "student_id": student_id,
            "skills": ["Python", "SQL"],
            "cgpa": 8.0,
            "target_roles": ["Software Engineer"],
            "completed_roadmaps": [],
            "interview_attempts": 0
        }
        return json.dumps(default_profile)
    
    with open(profile_path, "r", encoding="utf-8") as f:
        return f.read()

@mcp.tool()
def write_student_profile(student_id: str, profile_data_json: str) -> str:
    """Updates or creates a student's career profile in local storage.

    Args:
        student_id: The unique alphanumeric ID of the student.
        profile_data_json: A JSON string containing the profile details (e.g. skills, cgpa, target roles) to save.
    """
    ensure_data_dir()
    profile_path = os.path.join(DATA_DIR, f"{student_id}_profile.json")
    
    try:
        data = json.loads(profile_data_json)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Invalid JSON format: {str(e)}"})
        
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return json.dumps({"status": "success", "message": f"Profile saved for {student_id}."})

@mcp.tool()
def get_learning_resources(topic: str) -> str:
    """Retrieves standard learning guides and resource links for placement subjects.

    Args:
        topic: The subject topic name, e.g., 'DSA', 'SQL', 'DBMS', 'OOP', 'System Design'.
    """
    resources = {
        "dsa": "1. LeetCode (leetcode.com) - Recommend: NeetCode 150 Roadmap\n2. GeeksforGeeks DSA Self-Paced Course\n3. MIT 6.006 Introduction to Algorithms (YouTube)",
        "sql": "1. Mode Analytics SQL Tutorial (mode.com/sql-tutorial)\n2. SQLZoo Interactive Exercises (sqlzoo.net)\n3. LeetCode SQL 50 study plan",
        "dbms": "1. Database System Concepts by Silberschatz\n2. GateSmashers DBMS Playlist on YouTube\n3. GeeksforGeeks DBMS Notes",
        "oop": "1. Head First Design Patterns (Book)\n2. Refactoring.Guru Object-Oriented Design Principles\n3. Learncpp.com OOP guides",
        "system design": "1. The System Design Primer (GitHub repository by donnemartin)\n2. ByteByteGo by Alex Xu (bytebytego.com)\n3. Designing Data-Intensive Applications (Book by Martin Kleppmann)"
    }
    key = topic.lower().strip()
    return resources.get(key, f"No curated resources found for '{topic}'. Try searching online developer documentation.")

@mcp.tool()
def save_interview_log(student_id: str, role: str, feedback: str) -> str:
    """Appends an interview attempt result and feedback report to the student's log.

    Args:
        student_id: The unique alphanumeric ID of the student.
        role: The job role they interviewed for.
        feedback: The evaluation report and feedback from the interview.
    """
    ensure_data_dir()
    log_path = os.path.join(DATA_DIR, f"{student_id}_interviews.log")
    
    entry = f"\n=== Interview Log: {datetime.date.today().isoformat()} ===\nRole: {role}\nFeedback:\n{feedback}\n=============================\n"
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)
        
    return json.dumps({"status": "success", "message": "Interview feedback report appended to log."})

if __name__ == "__main__":
    mcp.run()
