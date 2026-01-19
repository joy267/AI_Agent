console.log("Hey Buddy, Mr. CA is here 😎");

import OpenAI from "openai";  // Importing OpenAI
import readline from 'node:readline/promises'  // Importing readline to get inputs from terminal

let expenceDB = []  // Empty array to store expences
let incomeDB = []  // Empty array to store income

const client = new OpenAI({  // Creating OpenAI client
    apiKey: process.env.GROQ_API_KEY,
    baseURL: "https://api.groq.com/openai/v1",
});

async function calling_agent() {  // Calling agent function

    const r1 = readline.createInterface({   // Creating readline interface to take inputs from users
        input: process.stdin,
        output: process.stdout
    })

    const agent_messages = [{  // Agent default messages

        role: 'system',
        content: `Your name is Mr. CA. You are a financial assistant. You are here to help the user with financial tasks. You are a AI agent that can perform tasks for the user.

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

        agent_messages.push({  // Pushing user question to agent messages
            role: 'user',
            content: userQuestion
        })

        // This is for Agent calling
        while (true) {

            const response = await client.chat.completions.create({  // Creating response from OpenAI
                model: "openai/gpt-oss-20b",
                messages: agent_messages,

                tools: [  // Giving tools or DB access to the agent
                    {
                        type: "function",
                        function: {
                            name: "getMonthlyExpences",  // Giving getMonthlyExpences function or DB access to the agent
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
                            name: "addExpences",  // Giving addExpences function or DB access to the agent
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
                            name: "addIncome",  // Giving addIncome function or DB access to the agent
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
                            name: "getBalance",  // Giving getBalance function or DB access to the agent
                            description: 'Get balance from the database',
                        }
                    }
                ]
            })

            agent_messages.push(response.choices[0].message) // Pushing agent response to agent messages

            const toolCalls = response.choices[0].message.tool_calls // Getting tool calls from agent response

            if (!toolCalls) {  // If there are no tool calls
                console.log(`Mr. CA: ${response.choices[0].message.content}`)
                break
            }

            for (const tool of toolCalls) {  // If there are tool calls
                const functionName = tool.function.name
                const functionArgs = JSON.parse(tool.function.arguments)

                let result = ""

                if (functionName === 'getMonthlyExpences') {  // If the function name is getMonthlyExpences
                    result = await getMonthlyExpences(functionArgs)
                } else if (functionName === 'addExpences') {  // If the function name is addExpences
                    result = await addExpences(functionArgs)
                } else if (functionName === 'addIncome') {  // If the function name is addIncome
                    result = await addIncome(functionArgs)
                } else if (functionName === 'getBalance') {  // If the function name is getBalance
                    result = await getBalance()
                }

                agent_messages.push({  // Pushing tool response to agent messages
                    role: 'tool',
                    content: result,
                    tool_call_id: tool.id
                })
            }
        }
    }

    r1.close() // Closing the readline interface
}

calling_agent()

async function getMonthlyExpences({ from, to }) {  // Getting monthly expences from the database

    // TODO: Get monthly expences from the database ...
    const expences = expenceDB.filter(expence => expence.date >= from && expence.date <= to)
    const total_expences = expences.reduce((total, expence_amount) => {
        return total + expence_amount
    }, 0)
    return `₹ ${total_expences}`
}

async function addExpences({ name, amount, date }) {  // Adding expence to the database

    // TODO: Add expence to the database ...
    expenceDB.push({ name, amount, date })
    return `Expence ${name} added successfully`
}

async function addIncome({ name, amount, date }) {  // Adding income to the database

    // TODO: Add income to the database ...
    incomeDB.push({ name, amount, date })
    return `Income ${name} added successfully`
}

async function getBalance() {  // Getting balance from the database
    const totalIncome = incomeDB.reduce((total, income_amount) => total + income_amount.amount, 0)
    const totalExpences = expenceDB.reduce((total, expence_amount) => total + expence_amount.amount, 0)

    return `₹ ${totalIncome - totalExpences}`
}
