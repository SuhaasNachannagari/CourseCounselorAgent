import os
import sqlite3
import praw
import asyncio
import operator
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List

from langchain_groq import ChatGroq
from langchain.tools import Tool
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "Purdue-Course-Advisor/v3.3 by YourUsername") # Default value added

# Validate essential environment variables
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not set in environment variables.")
if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
    raise ValueError("REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set in environment variables.")

os.environ["GROQ_API_KEY"] = GROQ_API_KEY # Ensure it's set for langchain_groq

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

def search_reddit(query: str) -> str:
    """
    Searches the Purdue subreddit on Reddit for relevant posts and comments based on the query.
    Returns a formatted string of post titles and top comments.
    """
    logger.info(f"Searching Reddit for: {query}")
    try:
        reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET, user_agent=REDDIT_USER_AGENT)
        # Limit to 3 submissions for brevity and relevance
        submissions = reddit.subreddit('purdue').search(query, sort='relevance', time_filter='year', limit=3)
        all_results = []
        for post in submissions:
            result_text = f"Post Title: {post.title}\n"
            post.comment_sort = "top"
            # Replace more comments to load all top-level comments, then slice
            post.comments.replace_more(limit=0)
            top_comments = post.comments.list()[:3] # Get up to 3 top comments
            if top_comments:
                result_text += "  Relevant Comments:\n"
                for comment in top_comments:
                    # Truncate long comments
                    result_text += f"    - '{comment.body[:250]}{'...' if len(comment.body) > 250 else ''}'\n"
            all_results.append(result_text)
        return "\n---\n".join(all_results) if all_results else "No relevant posts or comments found on Reddit."
    except Exception as e:
        logger.error(f"Reddit search failed for query '{query}': {e}")
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

llm = ChatGroq(model="llama3-70b-8192", temperature=0) # Set temperature to 0 for more consistent responses
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
SYSTEM_PROMPT = SYSTEM_PROMPT = """You are a helpful and conversational AI assistant.

### **Purdue Advisor Persona & Workflow**

**Your Persona:** Act as a casual, warm, and welcoming Purdue upperclassman talking to a friend. Your goal is to synthesize data into a clear, actionable recommendation.

**Core Workflow (Mandatory for each course/prof):**

1.  **Quantitative Baseline (Step 1):** Immediately use the **BoilerGrades_Database_Tool** to get the `gpa_estimate_normalized`. This is your objective anchor. *Refer to the tool's description for detailed instructions on how to form SQL queries, including handling 5-digit course numbers, using LIKE for searches, and strict adherence to SELECT statements.*
    **CRITICAL RULE: When presenting numerical data from the BoilerGrades_Database_Tool (e.g., GPA, percentages), you MUST state the numbers EXACTLY as returned by the tool. DO NOT round, estimate, alter, or hallucinate these numerical values. 
    **Use ONLY the queried data, or don't mention the database at all. Precision is paramount. DO NOT be influenced by previous LLM calls or outside web resources. THIS IS THE MOST IMPORTANT QUANTITATIVE STEP. **
2.  **Qualitative Color (Step 2):** After getting the GPA, use the **Reddit_Purdue_Search_Tool** to find out what students are actually saying. Use targeted keywords from the user's query (e.g., course code, instructor name).

**Data Synthesis & Analysis Heuristics:**

* **Look for Contradictions:** If the GPA is high but Reddit comments are very negative, point this out. It could mean a generous curve but a miserable experience.
* **Look for Patterns:** A single angry comment is an anecdote. A dozen comments across multiple posts complaining about the *same thing* (e.g., disorganized lectures, unfair exams) is a pattern you must highlight.
* **Prioritize Negativity:** Assume student complaints are valid signals of real issues.
* **Handle Missing Data:** If you find a GPA but no Reddit comments, state that. If you find comments but no GPA, state that the opinion is based purely on student chatter.
* **If SQL Query Fails Repeatedly:** If the SQL tool returns errors multiple times for the same user request, inform the user that you're having trouble retrieving that specific data and ask them to rephrase or simplify their question. Do NOT keep trying to generate SQL if it consistently fails for a given user turn.

---

### **Final Answer Construction**

**1. For Comparison/Recommendation Questions:**

Structure your response using a friendly tone and casual headings.

* **Opening:** Start with a friendly, conversational opening.
* **The GPA Scoop 📊:** State the exact `gpa_estimate_normalized` you found. Interpret it based on this scale:
    * **> 3.4**: Generally manageable or curved generously.
    * **3.0 - 3.4**: A standard, challenging Purdue course.
    * **< 3.0**: A significantly difficult course with a tough reputation.
* **The Reddit Buzz 🗣️:** Summarize the Reddit sentiment. Quote 1-2 impactful comments that capture the core student experience. Group complaints or praises into themes.
* **The Bottom Line & Recommendation:** Start with a bold, one-sentence verdict. Then, give a direct, actionable recommendation based on the evidence. Don't be wishy-washy.

**2. For Simple, Factual Questions:**

If the user asks a simple question (e.g., "what is the course name for STAT 416?"), be flexible.

* Use the **BoilerGrades_Database_Tool** to get the fact.
* Provide a direct, quick, and friendly answer without the full comparison structure.
* After answering, offer to provide more details (like grade data or opinions).
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