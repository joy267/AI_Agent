# Simple LangGraph Bot without any memory

from typing import TypedDict, List
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq        
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
import os

load_dotenv()

class AgentState(TypedDict):
    messages: List[HumanMessage]

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY")) 

def process(state: AgentState) -> AgentState:
    response = llm.invoke(state["messages"])           
    print(f"Agent: {response.content}")
    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("process", process)
workflow.add_edge(START, "process")
workflow.add_edge("process", END)

graph = workflow.compile()

while True:
    user_input = input("User: ")
    if user_input.lower() == "exit":
        break
    graph.invoke({"messages": [HumanMessage(content=user_input)]})