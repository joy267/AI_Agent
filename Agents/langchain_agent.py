# Remove warnigns from terminal
import warnings
warnings.filterwarnings("ignore")  

# Print greeting message
print("Hey Buddy, Miss. Earth 🌍 is here!")

import os
import requests
from datetime import datetime
from langchain.agents import create_agent
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

current_datetime = datetime.now().strftime("%A, %d %B %Y %I:%M %p")

# Weather tool configuration
@tool("get_weather")
def get_weather(city: str) -> str:
    """Get the current weather in a city."""

    try:
        response = requests.get(
            f"https://wttr.in/{city}?format=j1",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            condition = data["current_condition"][0]["weatherDesc"][0]["value"]
            temperature = data["current_condition"][0]["temp_C"]
            humidity = data["current_condition"][0]["humidity"]
            windspeed = data["current_condition"][0]["windspeedKmph"]
            feels_like = data["current_condition"][0]["FeelsLikeC"]
            return f"The weather in {city} is {condition}, {temperature}°C (feels like {feels_like}°C), humidity {humidity}%, wind {windspeed} km/h."
        else:
            return f"Could not fetch weather for {city}. Try again."
    except requests.exceptions.ConnectionError:
        return f"Connection failed while fetching weather for {city}. Please check your internet or try again."
    except requests.exceptions.Timeout:
        return f"Request timed out for {city}. The weather service may be slow, please try again."
    except Exception as e:
        return f"Unexpected error: {str(e)}"

# print(get_weather.invoke("kolkata"))

# Configure LLM
agent = create_agent(
    model = "groq:llama-3.3-70b-versatile",
    tools = [get_weather],
    system_prompt = f"Your name is Miss. Earth. You are a weather assistant. You are here to help the user for weather related queries. Your current datetime is {current_datetime}.",
)

#  Use thread_id to let the agent manage memory internally
config = {"configurable": {"thread_id": "weather-session-1"}}

print("Type 'exit' or 'bye' to quit.\n")
# Loop for chat 
while True:
    print("-"*30 + "\n")
    user_input = input("You: ").strip()
    if user_input.lower() in ["exit", "bye"]:
        print("Miss. Earth 🌍 : Goodbye! 👋")
        break

    # Invoke the agent
    response = agent.invoke({"messages": [{"role": "user", "content": user_input}]}, config = config)

    # Extract assistant response
    try:
        assistant_response = response["messages"][-1].content
    except Exception as e:
        assistant_response = "Sorry, I'm having trouble understanding you. Please try again. 😔" + str(e)

    # Print assistant response
    print(f"\nMiss. Earth 🌍 : {assistant_response}\n")
