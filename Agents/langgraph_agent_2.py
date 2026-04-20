# Simple LangGraph Bot with some memory

from typing import TypedDict, List, Union
from langchain_core.messages import HumanMessage, AIMessage
from langchain_groq import ChatGroq        
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
import os

load_dotenv()

class AgentState(TypedDict):
    messages: List[Union[HumanMessage, AIMessage]]

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))

def process(state: AgentState) -> AgentState:
    """Process the user input and generate a response."""

    response = llm.invoke(state["messages"])

    state["messages"].append(AIMessage(content=response.content))
    print(f"\nAgent: {response.content}\n")
    #print("Current State: ", state["messages"])
    return state

graph = StateGraph(AgentState)
graph.add_node("process", process)
graph.add_edge(START, "process")
graph.add_edge("process", END)

agent = graph.compile()

conversation_history = []

user_input = input("You: ")

while user_input.lower() != "exit":
    conversation_history.append(HumanMessage(content=user_input))
    result = agent.invoke({"messages": conversation_history})
    conversation_history = result["messages"]
    user_input = input("You: ")
    
with open("conversation_history.txt", "w") as f:  # Store the conversation history in a file
    f.write("Your Conversation History Log: \n")

    for message in conversation_history:
        if isinstance(message, HumanMessage):
            f.write(f"You: {message.content}\n")
        elif isinstance(message, AIMessage):
            f.write(f"Agent: {message.content}\n\n")
    f.write("End of Conversation")

print("Conversation history saved to conversation_history.txt")