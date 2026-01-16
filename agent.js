console.log("Hey Buddy, Agent J is here 😎");

import OpenAI from "openai";
import readline from 'node:readline/promises'

let expenceDB = []
let incomeDB = []

const client = new OpenAI({
    apiKey: process.env.GROQ_API_KEY,
    baseURL: "https://api.groq.com/openai/v1",
});

// let user_message = "I bought a macbook pro for 150000"

async function calling_agent() {
    const r1 = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    })

    const agent_messages = [{
        role: 'system',
        content: `Your name is Agent J. You are a helpful assistant. You are here to help the user with their tasks. You are a AI agent that can perform tasks for the user.

        You have access to the following tools:
        1. getMonthlyExpences({from, to}): string // Get monthly expences from the database
        2. addExpences({name, amount, date}): string // Add expences to the database   
        3. addIncome({name, amount, date}): string // Add income to the database  
        4. getBalance(): string // Get balance from the database    

        Note: The current datetime is ${new Date().toDateString()}`
    }];

    // This is for User calling
    while (true) {

        const userQuestion = await r1.question("User: ")

        if (userQuestion === 'exit') {
            break
        }

        agent_messages.push({
            role: 'user',
            content: userQuestion
        })

        // This is for Agent calling
        while (true) {
            const response = await client.chat.completions.create({
                model: "openai/gpt-oss-20b",
                messages: agent_messages,
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
                                    },
                                },
                                required: ["from", "to"]
                            }
                        }
                    },
                    {
                        type: "function",
                        function: {
                            name: "addExpences",
                            description: 'Add expences to the database',
                            parameters: {
                                type: 'object',
                                properties: {
                                    name: {
                                        type: 'string',
                                        description: 'Name of the expence',
                                    },
                                    amount: {
                                        type: 'string',
                                        description: 'Amount of the expence',
                                    },
                                    date: {
                                        type: 'string',
                                        description: 'Date of the expence',
                                    },
                                },
                                required: ["name", "amount", "date"]
                            }
                        }
                    },
                    {
                        type: "function",
                        function: {
                            name: "addIncome",
                            description: 'Add income to the database',
                            parameters: {
                                type: 'object',
                                properties: {
                                    name: {
                                        type: 'string',
                                        description: 'Name of the income',
                                    },
                                    amount: {
                                        type: 'string',
                                        description: 'Amount of the income',
                                    },
                                    date: {
                                        type: 'string',
                                        description: 'Date of the income',
                                    },
                                },
                                required: ["name", "amount", "date"]
                            }
                        }
                    },
                    {
                        type: "function",
                        function: {
                            name: "getBalance",
                            description: 'Get balance from the database',
                        }
                    }
                ]
            })

            agent_messages.push(response.choices[0].message)

            const toolCalls = response.choices[0].message.tool_calls

            if (!toolCalls) {
                console.log(`Agent J: ${response.choices[0].message.content}`)
                break
            }

            for (const tool of toolCalls) {
                const functionName = tool.function.name
                const functionArgs = JSON.parse(tool.function.arguments)

                let result = ""

                if (functionName === 'getMonthlyExpences') {
                    result = await getMonthlyExpences(functionArgs)
                } else if (functionName === 'addExpences') {
                    result = await addExpences(functionArgs)
                } else if (functionName === 'addIncome') {
                    result = await addIncome(functionArgs)
                } else if (functionName === 'getBalance') {
                    result = await getBalance()
                }

                agent_messages.push({
                    role: 'tool',
                    content: result,
                    tool_call_id: tool.id
                })
            }
        }
    }

    r1.close()
}

calling_agent()

async function getMonthlyExpences({ from, to }) {

    // TODO: Get monthly expences from the database ...
    const expences = expenceDB.filter(expence => expence.date >= from && expence.date <= to)
    const total_expences = expences.reduce((total, expence_amount) => {
        return total + expence_amount
    }, 0)
    return `₹ ${total_expences}`
}

async function addExpences({ name, amount, date }) {

    // TODO: Add expence to the database ...
    expenceDB.push({ name, amount, date })
    return `Expence ${name} added successfully`
}

async function addIncome({ name, amount, date }) {

    // TODO: Add income to the database ...
    incomeDB.push({ name, amount, date })
    return `Income ${name} added successfully`
}

async function getBalance() {
    const totalIncome = incomeDB.reduce((total, income_amount) => total + income_amount.amount, 0)
    const totalExpences = expenceDB.reduce((total, expence_amount) => total + expence_amount.amount, 0)

    return `₹ ${totalIncome - totalExpences}`
}
