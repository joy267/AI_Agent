from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
import os

load_dotenv()

# This is the global variable to store document content
document_content = ""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


@tool
def update(content: str) -> str:
    """ Updates the document with the provided content."""
    global document_content
    document_content = content
    return f"Document has been updated successfully! The current content is: \n{document_content}"

@tool
def save(filename: str) -> str:
    """ Save the current document to a text file and finish the process.
    
    Args:
        filename: Name for the text file.
    """
    global document_content

    if not filename.endswith(".txt"):
        filename = f"{filename}.txt"

    try:
        with open(filename, 'w') as file:
            file.write(document_content)
            print(f"\n Document has been saved to: {filename}")
            return f"Document has been saved to: {filename}"

    except Exception as e:
        print(f"\n Error saving document: {str(e)}")
        return f"Error saving document: {str(e)}"

tools = [update, save]

model = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=os.getenv("GROQ_API_KEY")).bind_tools(tools)

def our_agent(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content = f"""
    You are Drafter, a helpful writing assistant. You are going to help the user update and modify the documents.
    
    Instructions:
    - If the user wants you to save the document, call the save tool with the filename.
    - If the user wants you to update the document, call the update tool with the content.
    - Make sure to always show the current document state after updating it.

    The current document is: {document_content}
    """)

    if not state["messages"]:
        user_input = "I'm ready to help you update a document. What would you like to work on first?"
        user_message = HumanMessage(content = user_input)
    else:
        user_input = input("\nWhat would you like to do with the document? ")
        print(f"\n User: {user_input}")
        user_message = HumanMessage(content=user_input)

    all_messages = [system_prompt] + list(state["messages"]) + [user_message]

    response = model.invoke(all_messages)

    print(f"\n AI: {response.content}")
    if hasattr(response, "tool_calls") and response.tool_calls:
        print(f"\n Using Tools: {[tc['name'] for tc in response.tool_calls]}")

    return {"messages": list(state["messages"]) + [user_message, response]}

def should_continue(state: AgentState) -> str:
    """Determine if we should continue or end the conversation."""

    messages = state["messages"]

    if not messages:
        return "continue"

    # This looks for the most recent tool message ...

    for message in reversed(messages):
        # ... and checks if this is a ToolMessages resulting from save
        if (isinstance(message, ToolMessage) and
            "saved" in message.content.lower() and
            "document" in message.content.lower()):
            return "end"  # goes to the end edge which leads to the endpoint

    return "continue"

def print_messages(messages):
    """Function I made to print the messages in a readable format"""

    if not messages:
        return
    
    for message in messages[-3:]:
        if isinstance(message, ToolMessage):
            print(f"\n TOOL RESULT: {message.content}")

graph = StateGraph(AgentState)

graph.add_node("agent", our_agent)
graph.add_node("tools", ToolNode(tools))

graph.set_entry_point("agent")

graph.add_edge("agent", "tools")

graph.add_conditional_edges(
    "tools",
    should_continue,
    {
        "continue": "agent",
        "end": END
    },
)

app = graph.compile()

def run_document_agent():
    print("\n ==== Drafter Agent ====")

    state = {"messages": []}

    for step in app.stream(state, stream_mode = "values"):
        if "messages" in step:
            print_messages(step["messages"])
    
    print("\n ==== Drafter Finish ==== ")

if __name__ == "__main__":
    run_document_agent()