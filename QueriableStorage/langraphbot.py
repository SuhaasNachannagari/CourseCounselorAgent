import os
import sqlite3
import praw
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.tools import Tool
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_community.utilities.sql_database import SQLDatabase
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage
import asyncio
import operator

# --- LangGraph Imports ---
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# --- SETUP: Load API Keys & Credentials ---
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY") # type: ignore

# --- Reddit API Credentials ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = "Purdue-Course-Advisor/v3.3 by YourUsername"

# ==============================================================================
# 1. DEFINE THE TOOLS
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
# 2. SETUP THE STATEFUL GRAPH
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
# 3. RUN THE CONVERSATIONAL AGENT
# ==============================================================================

async def main():
    print("\n--- Purdue Course Advisor (LangGraph Edition) is ready! ---")
    print("This agent is now more robust for handling courses from all departments.\n")
    
    system_prompt = """You are a helpful but critical Purdue course advisor agent. Your goal is to give students the "real story" about a course's difficulty by synthesizing data and student chatter.

**YOUR PROCESS (Follow these steps IN ORDER):**
1.  **Analyze the user's query** to identify all mentioned professors and courses (including their subject, like 'CS' or 'STAT').
2.  **For EACH course/professor combination, ALWAYS start with the `BoilerGrades_Database_Tool`** to get the `gpa_estimate_normalized`. This is your quantitative baseline.
3.  **SECOND, use the `Reddit_Purdue_Search_Tool`** for each combination to gather qualitative student opinions.
4.  **FINALLY, synthesize the results** from all tools into a comprehensive answer.

**HEURISTICS FOR ANALYSIS:**
- A `gpa_estimate_normalized` below 3.0 suggests a challenging course.
- On Reddit, actively look for the most negative and critical comments first. Assume student complaints are valid.

**FINAL ANSWER INSTRUCTIONS:**
- State the exact average GPA you found and interpret it.
- Summarize the Reddit opinions, leading with the most critical comments. Quote them if they are impactful.
- Make a definitive claim about the course difficulty or professor comparison, using the GPA and Reddit comments as direct evidence."""

    conversation_history = [AIMessage(content=system_prompt)]
    
    try:
        while True:
            user_input = input("Enter your query (or type 'exit' to quit): ")
            if user_input.lower() == 'exit':
                break
            
            conversation_history.append(HumanMessage(content=user_input))

            response = await graph.ainvoke({"messages": conversation_history})
            
            final_answer = response['messages'][-1]
            print("\n--- FINAL ANSWER ---")
            print(final_answer.content)
            print("\n" + "="*50 + "\n")

            conversation_history.append(final_answer)

    except KeyboardInterrupt:
        print("\nAgent stopped by user.")

if __name__ == "__main__":
    asyncio.run(main())
