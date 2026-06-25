# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import datetime
import json
import re
from zoneinfo import ZoneInfo
from typing import Any, AsyncGenerator
from google.adk.agents import Agent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.tools import AgentTool, ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.workflow import Workflow, node, START
from google.genai import types

from app.config import config

# =====================================================================
# MCP SERVER INTEGRATION
# =====================================================================

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")],
        ),
    )
)

# =====================================================================
# SPECIALIZED LLM SUB-AGENTS (Called via AgentTool by the Orchestrator)
# =====================================================================

career_profile_agent = Agent(
    name="career_profile_agent",
    model=Gemini(model=config.model),
    instruction="""
    You are the Career Profile Agent for CareerForge AI.
    Your task is to analyze the user's resume/profile details.
    
    Responsibilities:
    - Assess Resume Quality (Score out of 100).
    - Analyze ATS Compatibility (Score out of 100).
    - Extract skills (languages, frameworks, databases, tools).
    - Identify key missing skills for the user's target career role.
    - Evaluate eligibility for major companies (TCS, Infosys, Wipro, Accenture, Amazon, Google) based on standard eligibility metrics like CGPA and skill alignment.
    
    Generate a detailed Profile Readiness Report outlining strengths, weaknesses, and eligibility.
    """,
    description="Analyzes resumes/profiles, scores ATS compatibility, extracts skills, and checks placement eligibility for major tech companies.",
    tools=[mcp_toolset],
)

learning_roadmap_agent = Agent(
    name="learning_roadmap_agent",
    model=Gemini(model=config.model),
    instruction="""
    You are the Personalized Learning Agent for CareerForge AI.
    Your task is to create custom, adaptive learning plans (weekly, monthly, or 90-day roadmaps).
    
    Responsibilities:
    - Map out curriculum topics: DSA (Arrays, Trees, DP, Graphs), OOP, DBMS, SQL, Operating Systems, Networks, and System Design.
    - Recommend high-quality learning resources (documentation, tutorials, practice platforms).
    - Set specific, measurable learning milestones based on target roles (e.g. Frontend, Backend, DevOps, Data Analyst, Software Engineer).
    
    Return a structured roadmap outlining the priority topics, weekly plan, and milestones.
    """,
    description="Creates structured weekly/monthly personalized study roadmaps covering DSA, SQL, DBMS, and core CS subjects.",
    tools=[mcp_toolset],
)

# =====================================================================
# ORCHESTRATOR TOOLS
# =====================================================================

def start_mock_interview(role: str, tool_context: ToolContext) -> dict:
    """Initiates a mock interview session for the specified role.
    
    Args:
        role: The job role to practice the interview for (e.g. Software Engineer, Data Analyst, Cloud Engineer).
        
    Returns:
        A dict indicating the setup status.
    """
    tool_context.state["route_to_interview"] = True
    tool_context.state["interview_role"] = role
    return {"status": "success", "message": f"Mock interview initiated for role: {role}. Preparing questions..."}

# =====================================================================
# ORCHESTRATOR AGENT
# =====================================================================

orchestrator_instruction = """
You are the CareerForge AI Orchestrator, an intelligent career mentor helping students achieve placement success.
Your goal is to coordinate specialized coaches to answer student queries, review resumes, build roadmaps, and conduct mock interviews.

Available Tools:
- career_profile_agent: Use this tool to analyze resumes, score ATS compatibility, extract skills, or check company placement eligibility.
- learning_roadmap_agent: Use this tool to generate weekly/monthly study schedules, DSA roadmaps, SQL practice guides, or core CS preparation guides.
- start_mock_interview: Use this tool if the user explicitly requests to start a mock interview, practice questions, or practice interviews for a specific role.

Instructions:
- If the user wants a mock interview, call 'start_mock_interview' immediately with their target role.
- For profile/resume/eligibility queries, call 'career_profile_agent'.
- For study roadmaps/plans, call 'learning_roadmap_agent'.
- If the user's request is a general query (like greeting, explaining how the platform works, or general encouragement), reply directly without calling any tools.
- Maintain a helpful, professional, and coaching-oriented tone.
"""

orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=Gemini(model=config.model),
    instruction=orchestrator_instruction,
    tools=[
        AgentTool(career_profile_agent),
        AgentTool(learning_roadmap_agent),
        start_mock_interview,
    ],
)

# =====================================================================
# GRAPH FUNCTION NODES
# =====================================================================

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Filters incoming prompts for PII scrubbing and injection detection."""
    text = ""
    if isinstance(node_input, types.Content):
        text = "".join([part.text for part in node_input.parts if part.text])
    elif isinstance(node_input, str):
        text = node_input
    
    # 1. PII Scrubbing
    scrubbed_text = text
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    
    pii_found = False
    if re.search(email_pattern, scrubbed_text):
        scrubbed_text = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed_text)
        pii_found = True
    if re.search(phone_pattern, scrubbed_text):
        scrubbed_text = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed_text)
        pii_found = True
        
    # 2. Prompt Injection Detection
    injection_keywords = ["system prompt", "ignore previous instructions", "bypass", "jailbreak", "override"]
    injection_detected = False
    for kw in injection_keywords:
        if kw in text.lower():
            injection_detected = True
            break
            
    # 3. Academic Integrity Domain-Specific Rule
    cheating_detected = False
    cheating_keywords = ["leak exam", "hack exam", "copy answers", "cheat in test"]
    for kw in cheating_keywords:
        if kw in text.lower():
            cheating_detected = True
            break

    # Structured Audit Log
    log_data = {
        "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
        "severity": "CRITICAL" if (injection_detected or cheating_detected) else ("WARNING" if pii_found else "INFO"),
        "event": "security_checkpoint_evaluation",
        "pii_detected": pii_found,
        "prompt_injection_detected": injection_detected,
        "cheating_attempt_detected": cheating_detected,
        "original_length": len(text),
        "scrubbed_length": len(scrubbed_text)
    }
    # Printed to standard out as structured JSON for log systems
    print(f"AUDIT_LOG: {json.dumps(log_data)}")

    if injection_detected or cheating_detected:
        return Event(output="Security violation: content blocked.", route="SECURITY_EVENT", state={"security_alert": True})
        
    # Save user input to session state for dynamic prompt access if needed
    return Event(output=scrubbed_text, route="normal", state={"user_input": scrubbed_text})


def security_violation_handler(node_input: str) -> Event:
    """Handles cases where input fails the security checkpoint filters."""
    msg = "⚠️ Security Checkpoint Alert: Your input was flagged for potential prompt injection, academic cheating, or policy violations. Action has been logged in the audit system."
    return Event(
        output=msg,
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)])
    )


def check_routing(ctx: Context, node_input: Any) -> Event:
    """Decides if the workflow should route to the mock interview engine."""
    if ctx.state.get("route_to_interview"):
        ctx.state["route_to_interview"] = False
        return Event(output=node_input, route="interview")
    return Event(output=node_input, route="general")


@node(rerun_on_resume=True)
async def mock_interview_node(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Manages multi-turn mock interview practice using RequestInput."""
    istate = ctx.state.get("interview_state")
    
    if not istate or not istate.get("is_active"):
        role = ctx.state.get("interview_role", "Software Engineer")
        istate = {
            "is_active": True,
            "current_question_index": 0,
            "role": role,
            "questions": [
                f"Welcome to your mock interview for the {role} role! Let's start. Question 1: Tell me about yourself and your key technical projects.",
                "Excellent. Let's move to a technical question. Question 2: Explain the difference between a process and a thread, and when you would choose to design a multi-threaded system.",
                "Good. Behavioral question. Question 3: Describe a time you faced a major challenge in a project and how you resolved it."
            ],
            "answers": []
        }
        ctx.state["interview_state"] = istate
        
        # Pause and request first input
        yield RequestInput(
            interrupt_id="q_0",
            message=istate["questions"][0]
        )
        return

    idx = len(istate["answers"])
    interrupt_id = f"q_{idx}"
    
    # Save the submitted answer on resume
    if ctx.resume_inputs and interrupt_id in ctx.resume_inputs:
        answer = ctx.resume_inputs[interrupt_id]
        istate["answers"].append(answer)
        ctx.state["interview_state"] = istate
        idx += 1

    # Ask the next question if available
    if idx < len(istate["questions"]):
        next_q = istate["questions"][idx]
        next_interrupt = f"q_{idx}"
        yield RequestInput(
            interrupt_id=next_interrupt,
            message=next_q
        )
        return

    # Interview complete, reset the state and evaluate
    istate["is_active"] = False
    ctx.state["interview_state"] = istate

    # Format transcript for evaluation
    eval_prompt = f"""
    You are the CareerForge AI Interview Evaluator.
    Evaluate the student's mock interview performance for the role: {istate['role']}.
    
    Questions & Answers:
    """
    for q, a in zip(istate["questions"], istate["answers"]):
        eval_prompt += f"\nQ: {q}\nA: {a}\n"
        
    eval_prompt += """
    Evaluate details carefully. Calculate scores (out of 100) and justify:
    - Communication Score
    - Technical Score
    - Confidence Score
    - Interview Readiness Score
    Provide constructive feedback outlining strengths, areas for improvement, and actionable next steps.
    """

    client = Gemini(model=config.model)
    response = client.generate_content(contents=eval_prompt)
    feedback_text = response.text

    yield Event(
        output=feedback_text,
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"### Mock Interview Complete! 🎉\n\nHere is your performance feedback:\n\n{feedback_text}")]
        )
    )


def format_final_output(ctx: Context, node_input: Any) -> Event:
    """Formats the final text content of the agent workflow for client visualization."""
    text = ""
    if isinstance(node_input, types.Content):
        text = "".join([part.text for part in node_input.parts if part.text])
    elif isinstance(node_input, str):
        text = node_input
    else:
        text = str(node_input)
        
    return Event(
        output=text,
        content=types.Content(role="model", parts=[types.Part.from_text(text=text)])
    )

# =====================================================================
# ADK 2.0 WORKFLOW GRAPH DEFINITION
# =====================================================================

edges = [
    # Input filtering
    (START, security_checkpoint),
    (security_checkpoint, {
        "normal": orchestrator_agent,
        "SECURITY_EVENT": security_violation_handler
    }),
    
    # Orchestration routing decision
    (orchestrator_agent, check_routing),
    (check_routing, {
        "interview": mock_interview_node,
        "general": format_final_output
    }),
    
    # Terminal formatting consolidation
    (mock_interview_node, format_final_output),
    (security_violation_handler, format_final_output)
]

root_agent = Workflow(
    name="careerforge_workflow",
    edges=edges,
)

# App instance
app = App(
    name="app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True)
)
