import winston from "winston";
import * as path from "path";

const logDir = path.join(process.cwd(), "logs");

//  Store current test name (will be updated from fixtures)
let currentTestName = "";

// Function to set the current test name
export function setTestName(name: string) {
  currentTestName = name;
}

// Function to clear test name after execution
export function clearTestName() {
  currentTestName = "";
}

export const logger = winston.createLogger({
  level: "info",
  format: winston.format.combine(
    winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),

    // ⭐ Inject test name into each log message
    winston.format.printf(({ timestamp, level, message }) => {
      const testLabel = currentTestName
        ? ` [TEST: ${currentTestName}]`
        : "";

      return `${timestamp} [${level.toUpperCase()}]${testLabel} ${message}`;
    })
  ),

  transports: [
    new winston.transports.Console(),

    new winston.transports.File({
      filename: path.join(logDir, "execution.log"),
      level: "info",
    }),

    new winston.transports.File({
      filename: path.join(logDir, "error.log"),
      level: "error",
    }),
  ],
});

//  Custom reusable error log capture function
export function logError(error: unknown, customMessage = "An error occurred") {
  if (error instanceof Error) {
    logger.error(`${customMessage}: ${error.message}`);
    logger.error(`STACK TRACE: ${error.stack}`);
  } else {
    logger.error(`${customMessage}: ${JSON.stringify(error)}`);
  }
}
