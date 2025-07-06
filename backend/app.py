import os
import sqlite3
import praw
import asyncio
import operator
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List

# --- LangChain & Groq Imports ---
from langchain_groq import ChatGroq
from langchain.tools import Tool
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage

# --- LangGraph Imports ---
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# --- FastAPI Imports ---
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==============================================================================
# 1. SETUP: Load API Keys & Credentials
# ==============================================================================
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# --- Reddit API Credentials ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = "Purdue-Course-Advisor/v3.3 by YourUsername"

# ==============================================================================
# 2. DEFINE THE TOOLS
# ==============================================================================

# SQL Database Tool
db_file = "grades_improved.db"
if not os.path.exists(db_file):
    raise FileNotFoundError(f"Database file '{db_file}' not found.")
db = SQLDatabase.from_uri(f"sqlite:///{db_file}")

# --- UPDATED SQL TOOL DESCRIPTION WITH ADVANCED EXAMPLES ---
sql_database_tool = QuerySQLDatabaseTool(
    db=db,
    name="BoilerGrades_Database_Tool",
    description=(
        "Use this tool to query a SQLite database named 'grades' containing Purdue University course data.\n\n"
        "**DATABASE SCHEMA:**\n"
        "The `grades` table has the following important columns:\n"
        "- `subject` (TEXT): The course subject (e.g., 'CS', 'STAT').\n"
        "- `course_number` (INTEGER): The course number (e.g., 18000, 25200).\n"
        "- `title` (TEXT): The official title of the course.\n"
        "- `academic_period` (TEXT): The semester the course was offered (e.g., 'Fall 2023', 'Spring 2022').\n"
        "- `instructor` (TEXT): The name of the instructor(s).\n"
        "- `gpa_estimate_normalized` (REAL): The estimated GPA for the course section.\n"
        "- `a_pct`, `b_pct`, etc. (REAL): Columns representing the percentage of students who received each letter grade.\n\n"
        "**HOW TO BUILD QUERIES:**\n"
        "1.  **Use `WHERE` Extensively:** ALWAYS filter your queries using `WHERE` clauses based on the user's request. You can filter by `subject`, `course_number`, `instructor`, and `academic_period`.\n"
        "2.  **Combine Conditions:** When a user provides multiple details (e.g., course and professor), you MUST combine them with `AND`.\n"
        "3.  **Use `AVG()` for Averages:** When a user asks for an average GPA, you MUST use the `AVG()` function on the `gpa_estimate_normalized` column.\n"
        "4.  **Handle Instructor and Period Names:** ALWAYS use the `LIKE` operator for `instructor` and `academic_period` to ensure a match (e.g., `instructor LIKE '%Dunsmore%'`, `academic_period LIKE 'Fall%'`, `academic_period LIKE '%2022%'`).\n\n"
        "5.  **Handle shortened course names. Oftentimes CS250 means CS 25000, and ECE 2k1 means ECE 20001, decipher these shorthands before querying with 5 digits"
        "**QUERY EXAMPLES:**\n"
        "- **User asks for average GPA for a course:** 'What's the average GPA for CS 180?'\n"
        "  `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE subject = 'CS' AND course_number = 18000`\n"
        "- **User asks about a specific professor's section:** 'Tell me about CS 180 with Dunsmore'\n"
        "  `SELECT title, instructor, academic_period, gpa_estimate_normalized FROM grades WHERE subject = 'CS' AND course_number = 18000 AND instructor LIKE '%Dunsmore%'`\n"
        "- **User asks for a professor's GPA just in Fall semesters:** 'What is Dunsmore's average GPA in the fall for CS 180?'\n"
        "  `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%' AND academic_period LIKE 'Fall%'`\n"
        "- **User asks for a professor's GPA in a specific year:** 'What was the average GPA for classes taught by Dunsmore in 2022?'\n"
        "  `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%' AND academic_period LIKE '%2022%'`\n"
        "- **User asks for a professor's overall average GPA:** 'What is Professor Dunsmore's average GPA?'\n"
        "  `SELECT AVG(gpa_estimate_normalized) FROM grades WHERE instructor LIKE '%Dunsmore%'`\n"
        "- **User asks for a course title:** 'what is the course name for STAT 416?'\n"
        "  `SELECT DISTINCT title FROM grades WHERE subject = 'STAT' AND course_number = 41600`"
    )
)


# Reddit Search Tool
def search_reddit(query: str) -> str:
    print(f"\n---> Searching Reddit for: {query}\n")
    try:
        reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET, user_agent=REDDIT_USER_AGENT)
        submissions = reddit.subreddit('purdue').search(query, sort='relevance', time_filter='year', limit=2)
        all_results = []
        for post in submissions:
            result_text = f"Post Title: {post.title}\n"
            post.comment_sort = "top"
            post.comments.replace_more(limit=0)
            top_comments = post.comments.list()[:3]
            if top_comments:
                result_text += "  Relevant Comments:\n"
                for comment in top_comments:
                    result_text += f"    - '{comment.body[:250]}...'\n"
            all_results.append(result_text)
        return "\n---\n".join(all_results) if all_results else "No relevant posts or comments found."
    except Exception as e:
        return f"Error searching Reddit: {e}"

reddit_search_tool = Tool(
    name="Reddit_Purdue_Search_Tool",
    func=search_reddit,
    description="Use this tool to find qualitative student opinions on r/purdue. Search using simple keywords like 'Adams CS 250' or 'Sellke STAT 416'."
)

# List of all tools
tools = [sql_database_tool, reddit_search_tool]

# ==============================================================================
# 3. SETUP THE STATEFUL GRAPH
# ==============================================================================

# Initialize the Groq LLM and bind the tools to it for tool-calling
llm = ChatGroq(model="llama3-70b-8192")
llm_with_tools = llm.bind_tools(tools)

# Define the State for our graph
class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# Define the nodes for the graph
async def tool_calling_llm(state: State):
    """This node invokes the LLM with tool-calling capabilities."""
    print("---CALLING MODEL (ASYNC)---")
    response = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}

tool_node = ToolNode(tools)

# Build the graph
builder = StateGraph(State)
builder.add_node("tool_calling_llm", tool_calling_llm)
builder.add_node("tools", tool_node)
builder.add_edge(START, "tool_calling_llm")
builder.add_conditional_edges("tool_calling_llm", tools_condition)
builder.add_edge("tools", "tool_calling_llm")

graph = builder.compile()

# ==============================================================================
# 4. SETUP FASTAPI SERVER
# ==============================================================================

app = FastAPI()

# Configure CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, change to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# In-memory store for conversation histories
conversation_history = {}

# Define the request body model for type checking
class ChatRequest(BaseModel):
    message: str
    session_id: str = 'default'

@app.get("/health")
def health_check():
    """
    Simple endpoint for Elastic Beanstalk health checks.
    """
    return {"status": "ok"}

@app.post("/chat")
async def chat(chat_request: ChatRequest):
    """
    This endpoint receives a user's message, processes it with the LangGraph agent,
    and returns the AI's response.
    """
    user_input = chat_request.message
    session_id = chat_request.session_id

    if not user_input:
        return {"error": "No message provided"}

    # Initialize conversation history for a new session
    if session_id not in conversation_history:
        system_prompt = """You are a helpful and conversational AI assistant.

### **Behavior Guardrail (Primary Rule)**

First, analyze the user's query. If the request is clearly NOT about Purdue University courses, professors, or related academic topics (e.g., asking about cooking, history, movie recommendations, or general knowledge), you MUST drop the advisor persona. In these cases, answer as a general-purpose, helpful AI assistant and **DO NOT use any of your specialized tools**. Just answer the question directly.

If the query IS about Purdue academics, adopt the persona and follow the detailed instructions below.

---

### **Purdue Advisor Persona & Workflow**

**Your Persona:** Act as a casual, warm, and welcoming Purdue upperclassman talking to a friend. Your goal is to synthesize data into a clear, actionable recommendation.

**Core Workflow (Mandatory for each course/prof):**

1.  **Quantitative Baseline (Step 1):** Immediately use the `BoilerGrades_Database_Tool` to get the `gpa_estimate_normalized`. This is your objective anchor.
2.  **Qualitative Color (Step 2):** After getting the GPA, use the `Reddit_Purdue_Search_Tool` to find out what students are actually saying. Use targeted keywords.

**Data Synthesis & Analysis Heuristics:**

* **Look for Contradictions:** If the GPA is high but Reddit comments are very negative, point this out. It could mean a generous curve but a miserable experience.
* **Look for Patterns:** A single angry comment is an anecdote. A dozen comments across multiple posts complaining about the *same thing* (e.g., disorganized lectures, unfair exams) is a pattern you must highlight.
* **Prioritize Negativity:** Assume student complaints are valid signals of real issues.
* **Handle Missing Data:** If you find a GPA but no Reddit comments, state that. If you find comments but no GPA, state that the opinion is based purely on student chatter.

---

### **Final Answer Construction**

**1. For Comparison/Recommendation Questions:**

Structure your response using a friendly tone and casual headings.

* **Opening:** Start with a friendly, conversational opening.
* **The GPA Scoop 📊:** State the exact `gpa_estimate_normalized` you found. Interpret it based on this scale:
    * `> 3.4`: Generally manageable or curved generously.
    * `3.0 - 3.4`: A standard, challenging Purdue course.
    * `< 3.0`: A significantly difficult course with a tough reputation.
* **The Reddit Buzz 🗣️:** Summarize the Reddit sentiment. Quote 1-2 impactful comments that capture the core student experience. Group complaints or praises into themes.
* **The Bottom Line & Recommendation:** Start with a bold, one-sentence verdict. Then, give a direct, actionable recommendation based on the evidence. Don't be wishy-washy.

**2. For Simple, Factual Questions:**

If the user asks a simple question (e.g., "what is the course name for STAT 416?"), be flexible.

* Use the `BoilerGrades_Database_Tool` to get the fact.
* Provide a direct, quick, and friendly answer without the full comparison structure.
* After answering, offer to provide more details (like grade data or opinions).
"""
        conversation_history[session_id] = [AIMessage(content=system_prompt)]

    # Append the user's message to the history
    conversation_history[session_id].append(HumanMessage(content=user_input))

    # Properly await the asynchronous graph invocation
    response = await graph.ainvoke({"messages": conversation_history[session_id]})

    final_answer = response['messages'][-1]

    # Append the AI's response to the history for context in the next turn
    conversation_history[session_id].append(final_answer)

    return {"reply": final_answer.content}