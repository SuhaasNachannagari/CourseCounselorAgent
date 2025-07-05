import os
import json
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import AgentExecutor, Tool, create_tool_calling_agent # <-- The new agent creator
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory

# Silence the LangSmith warning. It's not an error.
os.environ["LANGCHAIN_TRACING_V2"] = "false"

def main():
    if "GOOGLE_API_KEY" not in os.environ:
        print("ERROR: GOOGLE_API_KEY environment variable not set.")
        return
        
    print("Initializing Gemini LLM and connecting to the database...")
    # Using the Pro model as it's slightly better at complex reasoning for tool use
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-pro-latest",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    db = SQLDatabase.from_uri("sqlite:///grades_improved.db")
    print("Database connection successful.")

    sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = sql_toolkit.get_tools()

    # --- THE NEW, SIMPLER PROMPT ---
    # We no longer need complex instructions for Thoughts and Actions.
    # We just define the agent's personality and its goal.
    system_prompt = """
    You are a friendly and helpful Purdue University course advisor named BoilerBot.
    Your goal is to provide comprehensive, welcoming, and encouraging advice to students.

    You have access to a database with historical grade data for Purdue courses.
    - Use the database tools to answer objective questions about GPA, grade distributions, and instructors.
    - Always be conversational and welcoming in your final response.
    - Use the chat history to understand the context of follow-up questions.
    """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        # This placeholder is where the agent's tool-calling history will go.
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # --- THE NEW, SMARTER AGENT ---
    # create_tool_calling_agent is a modern, reliable way to build agents.
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True
    )
    print("Smarter, Tool-Calling agent created successfully.")

    # --- THE STATEFUL CHAT LOOP (Unchanged) ---
    chat_history = ChatMessageHistory()

    print("\n🤖 BoilerBot is ready.")
    print("I should now have a working memory and be more reliable. Type 'exit' to quit.")

    while True:
        try:
            user_question = input("You: ")
            if user_question.lower() in ["exit", "quit"]:
                break
            
            # The invoke call is now simpler, as the prompt doesn't need the tool descriptions manually passed.
            response = agent_executor.invoke({
                "input": user_question,
                "chat_history": chat_history.messages
            })
            
            print(f"\nAgent: {response['output']}\n")

            chat_history.add_user_message(user_question)
            chat_history.add_ai_message(response['output'])

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()