console.log("Hello, Agent J is here 😎");

import OpenAI from "openai";

const client = new OpenAI({
    apiKey: process.env.GROQ_API_KEY,
    baseURL: "https://api.groq.com/openai/v1",
});

async function calling_agent() {
    const response_1 = await client.chat.completions.create({
        model: "openai/gpt-oss-20b",
        messages: [
            {
                role: 'system',
                content: `Your name is Agent J. You are a helpful assistant. You are here to help the user with their tasks. You are a AI agent that can perform tasks for the user.
                Note: The current datetime is ${new Date().toUTCString()}`
            },
            {
                role: 'user',
                content: "What is the total expences from 2025-01-01 to 2025-01-31?"
            }
        ],
        tools: [
            {
                type: "function",
                function: {
                    name: "getMonthlyExpences",
                    description: 'Get monthly expences from the database',
                    parameters: {
                        type: 'object',
                        properties: {
                            from: {
                                type: 'string',
                                description: 'From date to get the expences',
                            },
                            to: {
                                type: 'string',
                                description: 'To date to get the expences',
                            }
                        }
                    }
                }
            }
        ]
    })

    console.log(JSON.stringify(response_1.choices[0], null, 2))

    const toolCalls_1 = response_1.choices[0].message.tool_calls

    if (!toolCalls_1) {
        console.log(`Agent J: ${response_1.choices[0].message.content}`)
        return
    }

    for (const tool of toolCalls_1) {
        const functionName = tool.function.name
        const functionArgs = JSON.parse(tool.function.arguments)

        let result = ""

        if (functionName === 'getMonthlyExpences') {
            result = getMonthlyExpences(functionArgs)
        }

        const response_2 = await client.chat.completions.create({
            model: "openai/gpt-oss-20b",
            messages: [
                {
                    role: 'system',
                    content: `Your name is Agent J. You are a helpful assistant. You are here to help the user with their tasks. You are a AI agent that can perform tasks for the user.
                Note: The current datetime is ${new Date().toUTCString()}`
                },
                {
                    role: 'user',
                    content: "What is the total expences from 2025-01-01 to 2025-01-31?"
                },
                {
                    role: 'tool',
                    content: result,
                    tool_call_id: tool.id
                }
            ],
            tools: [
                {
                    type: "function",
                    function: {
                        name: "getMonthlyExpences",
                        description: 'Get monthly expences from the database',
                        parameters: {
                            type: 'object',
                            properties: {
                                from: {
                                    type: 'string',
                                    description: 'From date to get the expences',
                                },
                                to: {
                                    type: 'string',
                                    description: 'To date to get the expences',
                                }
                            }
                        }
                    }
                }
            ]
        })

        console.log(JSON.stringify(response_2.choices[0], null, 2))

    }

}
calling_agent()

async function getMonthlyExpences({ from, to }) {
    console.log(`Getting monthly expences from ${from} to ${to}`)

    // TODO: Get monthly expences from the database ...
    return '1000'
}