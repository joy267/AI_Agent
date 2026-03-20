import * as dotenv from "dotenv";

const ENV = process.env.ENV || "local";

// Try to load the environment file, fall back to staging if it fails
const result = dotenv.config({
  path: `.env.${ENV}`,
  override: true
});

// If local env file failed to load, try staging
if (result.error && ENV === "local") {
  dotenv.config({
    path: `.env.staging`,
    override: true
  });
}

export const ENV_CONFIG = {
  envName: result.error && ENV === "local" ? "staging" : ENV,
  APP_URL: process.env.APP_URL!,
  Test_User: process.env.Test_User!,
  Test_Pass: process.env.Test_Pass!,
  API_URL: process.env.API_URL!
};