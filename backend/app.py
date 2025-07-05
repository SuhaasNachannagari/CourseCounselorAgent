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

sql_database_tool = QuerySQLDatabaseTool(
    db=db,
    name="BoilerGrades_Database_Tool",
    description=(
        "Use this tool to get quantitative grade data about Purdue courses from the 'grades' table.\n"
        "**CRITICAL SCHEMA INSTRUCTIONS:**\n"
        "- The user will provide a course like 'CS 25000' or 'STAT 416'. You **MUST** identify the subject prefix (e.g., 'CS', 'STAT') and the course number from the user's query.\n"
        "- Your SQL query **MUST** use both of these conditions: `subject = 'DEPARTMENT_PREFIX'` AND `course_number = 12345`.\n"
        "- The user might provide the title of a course. Use 'WHERE title LIKE %CoursName*' and ask for subject prefix and number if duplicates or ambiguous naming"
        "- The main grade column is `gpa_estimate_normalized`.\n"
        "- For instructors, use `WHERE instructor LIKE '%Name%'`."
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
def tool_calling_llm(state: State):
    """This node invokes the LLM with tool-calling capabilities."""
    print("---CALLING MODEL---")
    response = llm_with_tools.invoke(state["messages"])
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
        system_prompt = """You are a helpful but critical Purdue course advisor agent. Your goal is to give students the "real story" about a course's difficulty by synthesizing data and student chatter.

**YOUR PROCESS (Follow these steps IN ORDER):**
1.  **Analyze the user's query** to identify all mentioned professors and courses (including their subject, like 'CS' or 'STAT').
2.  **For EACH course/professor combination, ALWAYS start with the `BoilerGrades_Database_Tool`** to get the `gpa_estimate_normalized`. This is your quantitative baseline,.
3.  **SECOND, use the `Reddit_Purdue_Search_Tool`** for each combination to gather qualitative student opinions.
4.  **FINALLY, synthesize the results** from all tools into a comprehensive answer. If there's specific comments and such, mention those.

**HEURISTICS FOR ANALYSIS:**
- A `gpa_estimate_normalized` below 3.0 suggests a challenging course.
- On Reddit, actively look for the most negative and critical comments first. Assume student complaints are valid.

**FINAL ANSWER INSTRUCTIONS:**
- State the exact average GPA you found and interpret it, and be sure to provide any names of descriptions for the class.
- Summarize the Reddit opinions, leading with the most critical comments. Quote them if they are impactful.
- Make a definitive claim about the course difficulty or professor comparison, using the GPA and Reddit comments as direct evidence."""
        conversation_history[session_id] = [AIMessage(content=system_prompt)]

    # Append the user's message to the history
    conversation_history[session_id].append(HumanMessage(content=user_input))

    # Properly await the asynchronous graph invocation
    response = await graph.ainvoke({"messages": conversation_history[session_id]})

    final_answer = response['messages'][-1]

    # Append the AI's response to the history for context in the next turn
    conversation_history[session_id].append(final_answer)

    return {"reply": final_answer.content}


# To run this server:
# In your terminal, navigate to the `backend` directory and run the following command:
# uvicorn app:app --reload --port 8080


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080)
