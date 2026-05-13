from time import process_time
from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv
import os
from langchain_core.messages import BaseMessage # The foundational class for all messages types in LangGraph
from langchain_core.messages import ToolMessage # Passes data from the tool calls to the LLM 
from langchain_core.messages import SystemMessage # Message for providing instructions to the LLM
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

load_dotenv()

# Annotated - Provides additional context without affecting the type itself
# We can provide metadata about the expected data type, format, and constraints
# This metadata is used by the model to generate the appropriate response

# email = Annotated[str, "This has to be a valid email format"]

# print(email.__metadata__)

# Sequence - To automatically handle the state updates for sequences such as by adding a new message or tool call in chat history

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


@tool
def add(a: int, b:int):
    """Adds two integers and returns the result."""
    return a + b

@tool
def sub(a: int, b:int):
    """Subtracts two integers and returns the result."""
    return a - b

@tool
def mul(a: int, b:int):
    """Multiplies two integers and returns the result."""
    return a * b

tools = [add, sub, mul]

model = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=os.getenv("GROQ_API_KEY")).bind_tools(tools)  # Give permission to the model to use tools


def model_call(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content = "You are my AI assistant, please answer my query to the best of your ability.")
    response = model.invoke([system_prompt] + state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"

graph = StateGraph(AgentState)
graph.add_node("our_agent", model_call)

tool_node = ToolNode(tools=tools)
graph.add_node("tools", tool_node)

graph.add_edge(START, "our_agent")

graph.add_conditional_edges(
    "our_agent",
    should_continue,
    {
        "continue": "tools",
        "end": END
    }
)

graph.add_edge("tools", "our_agent")

app = graph.compile()

def print_stream(stream):
    for s in stream:
        message = s["messages"][-1]
        if isinstance(message, tuple):
            print(message)
        else:
            message.pretty_print()

inputs = {"messages": [("user", "What is the sum of 100 + 255 and then subtract 50 from it and then multiply it by 2?")]}

print_stream(app.stream(inputs, stream_mode="values"))
