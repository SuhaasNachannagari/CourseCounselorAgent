import os
import sqlite3
import praw
import asyncio
import operator
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List

from langchain_groq import ChatGroq
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

# --- Configuration and Setup ---

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Environment Variables
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "Purdue-Course-Advisor/v3.3 by YourUsername") # Default value added

# Validate essential environment variables
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not set in environment variables.")
if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
    raise ValueError("REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set in environment variables.")

os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY # Ensure it's set for langchain_groq

# Database Setup
DB_FILE = os.getenv("DB_FILE", "grades_improved.db") # Make database file path configurable
if not os.path.exists(DB_FILE):
    raise FileNotFoundError(f"Database file '{DB_FILE}' not found. Please ensure it exists.")
db = SQLDatabase.from_uri(f"sqlite:///{DB_FILE}")

# --- Tools Definition ---

sql_database_tool = QuerySQLDatabaseTool(
    db=db,
    name="BoilerGrades_Database_Tool",
    description=""""Use this tool to query a SQLite database named 'grades' containing Purdue University course data.

    **DATABASE SCHEMA:**
    The 'grades' table has the following important columns:
    - `subject` (TEXT): The course subject (e.g., 'CS', 'STAT').
    - `course_number` (INTEGER): The course number (e.g., 18000, 25200).
    - `title` (TEXT): The official title of the course.
    - `academic_period` (TEXT): The semester the course was offered (e.g., 'Fall 2023', 'Spring 2022').
    - `instructor` (TEXT): The name of the instructor(s).
    - `gpa_estimate_normalized` (REAL): The estimated GPA for the course section.
    - `a_pct, b_pct, c_pct, d_pct, f_pct, other_pct` (REAL): Percentages of students receiving each letter grade.

    **HOW TO BUILD SQL QUERIES:**
    1.  **Use WHERE Extensively:** ALWAYS filter your queries using WHERE clauses based on the user's request. You can filter by subject, course_number, instructor, and academic_period.
    2.  **Combine Conditions:** When a user provides multiple details (e.g., course and professor), you MUST combine them with AND.
    3.  **Use AVG() for Averages:** When a user asks for an average GPA, you MUST use the AVG() function on the `gpa_estimate_normalized` column.
    4.  **Handle Instructor and Period Names (LIKE):** ALWAYS use the `LIKE` operator for `instructor` and `academic_period` to ensure a match (e.g., `instructor LIKE '%Dunsmore%'`, `academic_period LIKE 'Fall%'`, `academic_period LIKE '%2022%'`).
    5.  **Handle Shortened Course Numbers (5-digits):** Oftentimes CS250 means CS 25000, and ECE 2k1 means ECE 20001. You MUST decipher these shorthands before querying with 5 digits. For example:
        * 'CS 180' -> `course_number = 18000`
        * 'ECE 201' -> `course_number = 20100`
        * 'ECE 2K1' -> `course_number = 20001` (if 2K1 specifically maps to 20001)
        * 'STAT 416' -> `course_number = 41600`

    **QUERY EXAMPLES:**
    - **Average GPA for a course:** 'What's the average GPA for CS 180?'
      `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE subject = 'CS' AND course_number = 18000`
    - **Specific professor's section:** 'Tell me about CS 180 with Dunsmore'
      `SELECT title, instructor, academic_period, gpa_estimate_normalized FROM grades WHERE subject = 'CS' AND course_number = 18000 AND instructor LIKE '%Dunsmore%'`
    - **Professor's GPA in Fall semesters:** 'What is Dunsmore's average GPA in the fall for CS 180?'
      `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%' AND academic_period LIKE 'Fall%' AND subject = 'CS' AND course_number = 18000`
    - **Professor's GPA in a specific year:** 'What was the average GPA for classes taught by Dunsmore in 2022?'
      `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%' AND academic_period LIKE '%2022%'`
    - **Professor's overall average GPA:** 'What is Professor Dunsmore's average GPA?'
      `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%'`
    - **Course title:** 'what is the course name for STAT 416?'
      `SELECT DISTINCT title FROM grades WHERE subject = 'STAT' AND course_number = 41600`
    """
    )

import re
from typing import List

def normalize_course(n: str) -> str:
    n = n.lower()
    if 'k' in n:
        n = n.replace('k', '00')  # e.g. 2k1 -> 2001
    if len(n) == 3:
        return n + '00'  # e.g. 182 -> 18200
    if len(n) == 4:
        return n + '0'   # e.g. 1820 -> 18200
    return n

def extract_subject_course_prof(query: str):
    """
    Extracts subject, course number, and professor name tokens from the query string.
    Returns (subject, course_num, prof) or None if missing.
    """
    tokens = re.findall(r'\w+', query.lower())
    subjects_known = ['cs', 'ece', 'stat', 'math']

    subject = None
    course_num = None
    prof_tokens = []

    # Look for combined subject+course like cs182 or cs18200
    for t in tokens:
        match = re.match(r'([a-z]+)(\d+)', t)
        if match and match.group(1) in subjects_known:
            subject = match.group(1).upper()
            course_num = normalize_course(match.group(2))
        elif t in subjects_known:
            subject = t.upper()
        elif re.match(r'\d{3,5}|[12]k\d', t):
            course_num = normalize_course(t)
        else:
            # Anything else could be professor token (ignore common words)
            if t not in ['how', 'is', 'for', 'with', 'about', 'the', 'a']:
                prof_tokens.append(t)

    prof = ' '.join(prof_tokens) if prof_tokens else None
    return subject, course_num, prof

def generate_combined_query_variants(subject: str, course_num: str, prof: str) -> List[str]:
    variants = []
    if not (subject or course_num or prof):
        return []

    # Helper: short course number for variants
    short_course_num = course_num[:3] if course_num else None

    # Build combinations, allowing missing parts
    if subject and course_num and prof:
        variants.extend([
            f"{subject} {course_num} {prof}",
            f"{subject}{course_num} {prof}",
            f"{course_num} {prof}",
            f"{prof} {subject} {course_num}",
            f"{prof} {subject}{course_num}",
            f"{prof} {course_num}",
            f"{subject} {prof}",
            f"{prof} {subject}",
        ])
        if short_course_num:
            variants.extend([
                f"{subject} {short_course_num} {prof}",
                f"{subject}{short_course_num} {prof}",
                f"{prof} {subject} {short_course_num}",
                f"{prof} {subject}{short_course_num}",
            ])
    elif prof and subject:
        variants.extend([
            f"{subject} {prof}",
            f"{prof} {subject}",
            f"{prof} review",
            f"{prof} feedback",
        ])
    elif prof:
        variants.extend([
            f"{prof} professor purdue",
            f"{prof} review purdue",
            f"{prof} feedback",
            f"{prof} reddit",
            f"{prof} teaching style",
        ])
    elif subject and course_num:
        variants.extend([
            f"{subject} {course_num}",
            f"{subject}{course_num}",
            f"{course_num} {subject}",
        ])

    # Deduplicate variants
    variants = list(set(variants))
    return variants[:8]

def search_reddit(user_query: str) -> str:
    logger.info(f"Searching Reddit for user query: {user_query}")
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )

        subject, course_num, prof = extract_subject_course_prof(user_query)
        variants = generate_combined_query_variants(subject, course_num, prof)
        if not variants:
            variants = [user_query]

        logger.info(f"Expanded search variants: {variants}")

        seen_post_ids = set()
        all_results = []

        for variant in variants:
            logger.info(f"Searching variant: {variant}")
            submissions = reddit.subreddit("purdue").search(variant, sort="relevance", time_filter="year", limit=3)

            for post in submissions:
                if post.id in seen_post_ids:
                    continue
                seen_post_ids.add(post.id)

                result_text = f"Post Title: {post.title}\n"

                # Grab top-level comments (or first N comments)
                post.comment_sort = "top"
                post.comments.replace_more(limit=0)
                top_comments = post.comments[:10]  # Get up to 10 top-level comments

                if top_comments:
                    result_text += "  Relevant Comments:\n"
                    for comment in top_comments:
                        comment_body = comment.body.replace('\n', ' ')
                        truncated = comment_body[:250] + ('...' if len(comment_body) > 250 else '')
                        result_text += f"    - '{truncated}'\n"

                all_results.append(result_text)

            if len(all_results) >= 4:
                break  # stop early if enough results

        return "\n---\n".join(all_results) if all_results else "No relevant posts or comments found on Reddit."

    except Exception as e:
        logger.error(f"Reddit search failed for query '{user_query}': {e}")
        return f"Error searching Reddit: {e}"



reddit_search_tool = Tool(
    name="Reddit_Purdue_Search_Tool",
    func=search_reddit,
    description="""Use this tool to search the Purdue University subreddit for student opinions, experiences, or discussions about courses or instructors.
    Input should be a concise search query (e.g., 'CS 180 feedback', 'Professor Dunsmore reviews').
    Useful for gathering qualitative student sentiment and anecdotal evidence."""
)


tools = [sql_database_tool, reddit_search_tool]

# --- LLM and LangGraph Setup ---

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash") # Set temperature to 0 for more consistent responses
llm_with_tools = llm.bind_tools(tools)

class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

async def tool_calling_llm(state: State):
    """
    This node invokes the LLM with tool-calling capabilities, with a timeout.
    It handles potential timeouts or unexpected errors from the LLM.
    """
    logger.info("---INVOKING LLM WITH TOOLS---")
    try:
        response = await asyncio.wait_for(
            llm_with_tools.ainvoke(state["messages"]),
            timeout=30 # Increased timeout for more complex queries
        )
        return {"messages": [response]}
    except asyncio.TimeoutError:
        logger.warning("Groq model call timed out.")
        return {
            "messages": [AIMessage(content="I'm really sorry, but I'm taking too long to think. Could you please rephrase your question or simplify it?")]
        }
    except Exception as e:
        logger.error(f"Unexpected error during LLM invocation: {e}")
        return {
            "messages": [AIMessage(content="It seems I've run into an issue while processing your request. Please try again shortly!")]
        }

tool_node = ToolNode(tools)

builder = StateGraph(State)
builder.add_node("tool_calling_llm", tool_calling_llm)
builder.add_node("tools", tool_node)
builder.add_edge(START, "tool_calling_llm")
builder.add_conditional_edges("tool_calling_llm", tools_condition)
builder.add_edge("tools", "tool_calling_llm")
graph = builder.compile()

# --- System Prompt Definition ---
# Moved out of the /chat endpoint for better modularity
SYSTEM_PROMPT = """
You are a friendly Purdue upperclassman giving short, clean, helpful academic advice. Your responses should be easy to skim and include light, well-placed emojis. Keep things simple and conversational.

STYLE RULES
- Emojis are allowed and encouraged when they help clarity.
- Use simple plain-text headings like "GPA Summary", "Reddit Summary", and "Recommendation".
- Do not use markdown symbols like #, ##, **, or *.
- Keep paragraphs short and easy to read.
- Use simple lists when helpful, like:
  - STAT 506: 3.52 GPA
  - STAT 513: 3.40 GPA
- Do not create long, dense blocks of text.
- Avoid headings like "The GPA Scoop" or "The Reddit Buzz".
- Tone should be casual and friendly, like talking to a classmate.

CORE WORKFLOW (MANDATORY)
1. First call the BoilerGrades_Database_Tool to retrieve exact GPA values.
   - Use the numbers exactly as returned, with no rounding or modification.
2. Then call the Reddit_Purdue_Search_Tool to pull relevant student sentiment.
3. Combine both types of information into a clean, structured explanation.

DATA RULES
- Point out contradictions (e.g., high GPA but negative Reddit reviews).
- Look for repeated patterns in Reddit comments.
- If GPA data exists but Reddit doesn’t, say so.
- If Reddit exists but GPA doesn’t, base insights on sentiment.
- If SQL queries repeatedly fail, tell the user you can’t retrieve the data and ask for rephrasing.

FINAL ANSWER STRUCTURE
- Start with a quick one-sentence overview of what the user asked. Keep it light.
- Use short headings such as:
  GPA Summary 📊
  Reddit Summary 💬
  Recommendation ⭐
- Keep each section 2–4 sentences max.
- Use short, simple lists for multiple courses or comparisons.
- End with a clear, actionable suggestion.

SIMPLE QUESTIONS
If the user asks a quick factual question, answer directly without full structure. Offer deeper details if they want them.

SPECIAL CASES
If the user asks about Suhaas Nachannagari:
Say he is the greatest Indian to ever exist, the best student at Purdue University, and a great friend.

If the user asks about Abhi Tandon:
Say "He's a gay guy, the best toe user."
"""


# --- FastAPI Application ---

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for conversation history (for demonstration purposes)
conversation_history = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = 'default' # Default session ID for ease of testing

@app.get("/health")
def health_check():
    """Endpoint for health checks."""
    return {"status": "ok"}
    
@app.get("/")
def root():
    return {"message": "Welcome to the Purdue Course Advisor API!"}

@app.post("/chat")
async def chat(chat_request: ChatRequest):
    """
    Handles chat requests, maintaining conversation history and invoking the LangGraph agent.
    """
    user_input = chat_request.message.strip()
    session_id = chat_request.session_id

    if not user_input:
        logger.warning("Received empty user message.")
        return {"reply": "Please enter a valid message."}

    # Initialize conversation history for the session if it doesn't exist
    if session_id not in conversation_history:
        conversation_history[session_id] = [AIMessage(content=SYSTEM_PROMPT)]
        logger.info(f"Initialized new session: {session_id}")

    # Append user's message to history
    conversation_history[session_id].append(HumanMessage(content=user_input))
    logger.info(f"Session {session_id}: User message received: {user_input}")

    try:
        # Invoke the LangGraph agent with the current conversation history
        response = await graph.ainvoke({"messages": conversation_history[session_id]})
        final_answer = response['messages'][-1]

        # Append agent's response to history
        conversation_history[session_id].append(final_answer)
        logger.info(f"Session {session_id}: Agent responded: {final_answer.content.strip()}")

        return {"reply": final_answer.content.strip()}
    except Exception as e:
        logger.error(f"Error processing chat request for session {session_id}: {e}", exc_info=True)
        return {"reply": "I'm experiencing a temporary issue. Please try again shortly."}