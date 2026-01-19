console.log("Hey Buddy, Mr. Earth is here 😎")

import OpenAI from "openai"
import type { ChatCompletionMessageParam } from "openai/resources/chat";
import readline from "node:readline/promises"

const client = new OpenAI({
    apiKey: process.env.GROQ_API_KEY,
    baseURL: "https://api.groq.com/openai/v1"
})

async function weather_agent() {

    const userInput = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    })

    const agent_message: ChatCompletionMessageParam[] = [{

        role: 'system',
        content: `Your name is Mr. Earth. You are a weather assistant. You are here to help the user for weather related queries. 
        Your current datetime is ${new Date().toLocaleString()}

        You have access to the following tools:
        1. getWeatherDB(): string // Get weather from the database
        `
    }];

    while (true) {

        const userQuestion = await userInput.question('User:  ')

        if (userQuestion === 'exit') {
            break
        }

        agent_message.push({
            role: 'user',
            content: userQuestion
        })

        while (true) {

            const response = await client.chat.completions.create({
                model: 'openai/gpt-oss-20b',
                messages: agent_message,

                tools: [
                    {
                        type: 'function',
                        function: {
                            name: 'getWeatherDB',
                            description: 'Get weather from the database',
                            parameters: {
                                type: 'object',
                                properties: {
                                    location: {
                                        type: 'string',
                                        description: 'Location to get the weather',
                                    }
                                },
                                required: ['location']
                            }
                        }
                    }
                ]
            })

            const assistantMassage = response.choices[0]?.message

            if (assistantMassage) {
                agent_message.push(assistantMassage)
            }

            if (!assistantMassage?.tool_calls) {

                console.log(assistantMassage?.content)
                break
            }

            if (assistantMassage?.tool_calls) {
                for (const toolCall of assistantMassage.tool_calls) {

                    let result: string = ''

                    if (toolCall.type === 'function' && toolCall.function.name === 'getWeatherDB') {

                        const args = JSON.parse(toolCall.function.arguments)
                        result = await getWeatherDB(args.location)
                    }

                    agent_message.push({
                        role: 'tool',
                        content: result,
                        tool_call_id: toolCall.id
                    })
                }
            }
        }
    }
    userInput.close()
}

weather_agent()

async function getWeatherDB(location: string) {

    try {
        const weatherAPI = `https://api.tomorrow.io/v4/weather/forecast?location=${encodeURIComponent(location)}&apikey=E4h4TqGGPfzrdjyvWkJjqAl23RLoBxEo`

        const weatherResponse = await fetch(weatherAPI)

        if (!weatherResponse.ok) {
            throw new Error(`HTTP error! Status: ${weatherResponse.status}`)
        }
        const weatherData = await weatherResponse.json()

        // The API returns 'timelines' with different intervals
        const timelines = weatherData.timelines.hourly || weatherData.timelines.daily || []


        if (!timelines.length) {
            // Log what timelines are actually available
            console.log('Available timelines:', Object.keys(weatherData.timelines || {}))
            throw new Error('Weather data not found')
        }

        // Get current + next 4 hours (total 5 forecasts)
        const forecasts = timelines.slice(0, 10).map((item: any) => ({
            time: item.time,
            temperature: item.values.temperature,
            temperatureApparent: item.values.temperatureApparent,
            humidity: item.values.humidity,
            windSpeed: item.values.windSpeed,
            weatherCode: item.values.weatherCode,
            precipitationProbability: item.values.precipitationProbability
        }))

        const summary = {
            location: location,
            current: forecasts[0],  // Current weather
            upcoming: forecasts.slice(1)  // Next 4 hours
        }

        return JSON.stringify(summary, null, 2)
        // return JSON.stringify(weatherData, null, 2)

    } catch (error: any) {
        console.error('Error:', error.message)
        return error.message
    }
}
