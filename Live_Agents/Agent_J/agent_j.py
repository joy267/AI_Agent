from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv
from datetime import datetime
import os
import json
import re
import time
import logging
from langchain_core.messages import SystemMessage
from langchain_core.messages import BaseMessage
from langchain_core.messages import AIMessage
from langchain_core.messages import ToolMessage
# from langchain_groq import ChatGroq  # retired: see the commented-out summarizer below
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RetryPolicy
import requests
import openai
# from groq import BadRequestError, RateLimitError  # retired: see the commented-out salvage path below
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

load_dotenv()

# Internal logger for retry/diagnostic messages. These are NOT shown to the user
# by default. To see them while debugging, set the level to logging.DEBUG.
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("agent_j")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def model_call(state: AgentState) -> AgentState:
    today = datetime.now().strftime("%A, %B %d, %Y")
    system_prompt = SystemMessage(content=(
        f"You are Agent_J, a helpful and effective multi-tasking agent. "
        f"Today's date is {today}. "
        f"You always answer the user's query to the best of your ability. "
        f"Only use the search_web tool for current or real-time information. "
        f"Use the search_jobs tool when the user wants to find jobs, openings, "
        f"vacancies, or work-from-home roles — pass the job title and the "
        f"location as separate arguments. Each result already includes its key "
        f"details (skills, experience, requirements summary), a Job ID, and a "
        f"direct apply link; just present the results. "
        f"When the user asks for a blog post about ONE SPECIFIC job from "
        f"results already shown (they name the posting or quote its title/"
        f"company), call write_job_blog with that job's job_id — copy the "
        f"numeric Job ID printed with that result. Do NOT pass the job title "
        f"in that case, only the job_id. "
        f"Only when the user wants a general blog featuring several jobs for "
        f"a role (no specific posting picked) should you call write_job_blog "
        f"with title keywords and a location instead."
    ))
    response = llm_model.invoke([system_prompt] + state["messages"])
    return {"messages": [response]}

@tool
def get_weather(city: str) -> str:
    """Get the current weather for the given city."""
    url = f"https://wttr.in/{city}?format=3"
    response = requests.get(url)
    return response.text

@tool
def search_web(query: str) -> str:
    """Search the web for current, real-time information.
    Use this for recent events, news, prices, or any fact you don't already know."""

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": os.getenv("SEARCH_ENGINE_API_KEY"),
        "Content-Type": "application/json",
    }
    payload = {"q": query}

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    # Return the entire Serper response as JSON text.
    return json.dumps(data, indent=2, ensure_ascii=False)


# def _extract_jobs_and_cursor(payload: dict):
#     """search-v2 nests results differently from the other endpoints: the docs
#     refer to `data.cursor`, meaning `data` is an OBJECT holding both the jobs
#     array and the next-page cursor — whereas job-details/salary return `data`
#     as a flat list. This handles either shape and finds the jobs list even if
#     its key name varies, returning (jobs_list, cursor)."""
#     raw = payload.get("data")
#     cursor = payload.get("cursor")

#     # Shape A: data is already the list of jobs.
#     if isinstance(raw, list):
#         return raw, cursor

#     # Shape B: data is an object containing the jobs list + cursor.
#     if isinstance(raw, dict):
#         cursor = raw.get("cursor", cursor)
#         for key in ("jobs", "data", "results", "items"):
#             val = raw.get(key)
#             if isinstance(val, list):
#                 return val, cursor
#         # Fallback: first value that looks like a list of job objects.
#         for val in raw.values():
#             if isinstance(val, list) and (not val or isinstance(val[0], dict)):
#                 return val, cursor
#         return [], cursor

#     return [], cursor


# def _fetch_jobs(query, country, date_posted, work_from_home, max_results, max_pages):
#     """Fetch job dicts from search-v2, walking cursor pagination until the API
#     runs out of results, max_results is reached, or max_pages is hit. Returns
#     (jobs_list, error) where error is an exception/str or None. Shared by
#     search_jobs and write_job_blog."""
#     api_key = os.getenv("JSEARCH_API_KEY")
#     if not api_key:
#         return [], "JSEARCH_API_KEY is not set"

#     url = "https://api.openwebninja.com/jsearch/search-v2"
#     headers = {"x-api-key": api_key}

#     all_jobs = []
#     cursor = None
#     error = None

#     # Walk cursor pagination one page at a time until the API runs out of
#     # results, we have enough (max_results), or we hit the page cap (credits).
#     for _ in range(max(1, max_pages)):
#         params = {
#             "query": query,
#             "country": country,
#             "date_posted": date_posted,
#             "work_from_home": str(work_from_home).lower(),
#             "num_pages": 1,
#         }
#         if cursor:
#             params["cursor"] = cursor

#         try:
#             response = requests.get(url, headers=headers, params=params, timeout=30)
#             response.raise_for_status()
#             payload = response.json()
#         except Exception as e:
#             error = e
#             break  # stop paging but keep whatever we already collected

#         page_jobs, cursor = _extract_jobs_and_cursor(payload)
#         # Guard against any stray non-dict entries so formatters can't crash.
#         page_jobs = [j for j in page_jobs if isinstance(j, dict)]
#         all_jobs.extend(page_jobs)

#         if len(all_jobs) >= max_results:
#             all_jobs = all_jobs[:max_results]
#             break
#         if not cursor or not page_jobs:
#             break

#     return all_jobs, error


# ─── OLD JSearch-based search_jobs (kept for reference, replaced by the
# Active ATS version below). ───
# @tool
# def search_jobs(
#     query: str,
#     country: str = "in",
#     date_posted: str = "today",
#     work_from_home: bool = False,
#     max_results: int = 50,
#     max_pages: int = 10,
# ) -> str:
#     """Search for real-time job listings (Google for Jobs aggregate).
#     Walks the API's cursor pagination to gather results, stopping when the API
#     runs out of results, max_results is reached, or max_pages is reached.
#     Use this when the user wants to find jobs, openings, vacancies, or
#     work-from-home roles. Each result includes a Job ID that can be passed to
#     get_job_details for the full posting.
#
#     query: include job title AND location, e.g. "python developer in kolkata".
#     country: two-letter ISO code matching the location, e.g. "us", "in", "de".
#     date_posted: one of "all", "today", "3days", "week", "month".
#     work_from_home: True to return only remote / WFH jobs.
#     max_results: hard cap on total jobs returned (default 50).
#     max_pages: safety cap on pages pulled. Each page is up to 10 jobs and costs
#                1 API credit. Default 10."""
#
#     all_jobs, error = _fetch_jobs(
#         query, country, date_posted, work_from_home, max_results, max_pages
#     )
#     if not all_jobs:
#         if error:
#             return f"Job search failed: {error}"
#         return f"No jobs found for '{query}'."
#
#     lines = []
#     for i, job in enumerate(all_jobs, start=1):
#         title = job.get("job_title", "Unknown role")
#         company = job.get("employer_name", "Unknown company")
#
#         # search-v2 usually gives a combined job_location; fall back to parts.
#         loc = job.get("job_location") or ", ".join(
#             p for p in (job.get("job_city"), job.get("job_state"), job.get("job_country"))
#             if p
#         ) or "N/A"
#
#         # job_is_remote can be null even for remote roles; work_arrangement is
#         # the more reliable signal in this API.
#         is_remote = job.get("job_is_remote") is True or job.get("work_arrangement") == "remote"
#         remote = " (Remote)" if is_remote else ""
#         employment = job.get("job_employment_type", "")
#         posted = job.get("job_posted_at") or job.get("job_posted_at_datetime_utc") or "N/A"
#         link = job.get("job_apply_link", "N/A")
#         job_id = job.get("job_id", "N/A")
#
#         # Compact: a scannable summary line, with the long ID + apply link on an
#         # indented continuation so the main list stays easy to read.
#         summary = [f"{title} — {company}", f"{loc}{remote}", posted]
#         if employment:
#             summary.append(employment)
#         line = f"{i}. " + " | ".join(summary) + f"\n   ID: {job_id} | Apply: {link}"
#         lines.append(line)
#
#     # If we stopped early because of an error, the list is partial — still useful.
#     note = f" (partial: {error})" if error else ""
#     header = f"Found {len(all_jobs)} jobs for '{query}'{note}:\n\n"
#     return header + "\n".join(lines)

# ─── NEW job search: Active ATS API ──────────────────────────────────────────
# Jobs scraped directly from company ATS boards (Greenhouse, Oracle Cloud,
# Workday, Lever, ...). The endpoint returns a JSON ARRAY of job objects with
# rich AI-enriched fields (ai_key_skills, ai_requirements_summary, salary,
# work arrangement), so each result is already detailed — no follow-up
# details call is needed. Base URL + key are env-configurable:
#   FANTASTIC_JOBS_API_URL  default "https://data.fantastic.jobs/v1/active-ats"
#   FANTASTIC_JOBS_API_KEY  sent as "Authorization: Bearer <key>" (per API docs)

FANTASTIC_JOBS_API_URL = os.getenv(
    "FANTASTIC_JOBS_API_URL", "https://data.fantastic.jobs/v1/active-ats"
)

# Cache of every job record shown to the user in this session, keyed by the
# API's internal `id`. search_jobs fills it; write_job_blog(job_id=...) reads
# from it, so blogging a specific posting reuses the EXACT record the user saw
# — no re-search, no chance of a different job sneaking in. In-memory only, so
# it lives exactly as long as the MemorySaver conversation thread does.
LAST_JOBS: dict[int, dict] = {}


def _dedupe_jobs(jobs: list) -> list:
    """Drop duplicate job records, preserving order. Primary key is the API's
    internal `id`; records missing an id fall back to a fuzzy key of
    (title, organization/domain, first location) — which also collapses the
    same posting syndicated across multiple ATS sources."""
    seen = set()
    unique = []
    for job in jobs:
        jid = job.get("id")
        if jid is not None:
            key = ("id", jid)
        else:
            locs = job.get("locations_derived") or job.get("locations_alt") or []
            key = (
                "fuzzy",
                (job.get("title") or "").strip().lower(),
                (job.get("organization") or job.get("domain_derived") or "").strip().lower(),
                str(locs[0]).strip().lower() if locs else "",
            )
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def _request_active_jobs(params: dict):
    """Low-level GET against the Active ATS API with the given query params.
    Returns (jobs_list, error): error is a short human-readable string on
    failure, else None. Handles auth, response-shape tolerance, and dedupes
    the returned records. Shared by every higher-level fetch helper."""
    api_key = os.getenv("FANTASTIC_JOBS_API_KEY")
    if not api_key:
        return [], "FANTASTIC_JOBS_API_KEY is not set"

    # Per the API docs, auth is a Bearer token, NOT an x-api-key header.
    headers = {"Authorization": f"Bearer {api_key}"}

    # Always ask for the basic organization fields (industry, headcount, HQ,
    # founded date, description, recruitment-agency flag, ...) so the blog's
    # ABOUT THE COMPANY section can be grounded in real data instead of the
    # writer model guessing what the employer does.
    params = {**params, "include_basic_organization_details": "true"}

    try:
        response = requests.get(
            FANTASTIC_JOBS_API_URL, headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        return [], str(e)

    # The endpoint returns a top-level JSON array; tolerate a wrapped shape too.
    if isinstance(payload, list):
        jobs = payload
    elif isinstance(payload, dict):
        jobs = payload.get("data") or payload.get("jobs") or payload.get("results") or []
    else:
        jobs = []

    jobs = [j for j in jobs if isinstance(j, dict)]
    return _dedupe_jobs(jobs), None


def _fetch_active_jobs(title, location, time_frame, limit, offset):
    """Fetch raw job dicts from the Active ATS API by title/location search.
    Returns (jobs_list, error). Shared by the search_jobs tool and
    write_job_blog so both hit the API the same way."""
    params = {
        "title": title,
        "location": location,
        "time_frame": time_frame,
        "limit": limit,
        "offset": offset,
    }
    return _request_active_jobs(params)


def _fetch_job_by_id(job_id: int):
    """Fetch ONE job record by the API's internal id (the `id` query filter).
    Used as a fallback when a job_id isn't in the LAST_JOBS cache — e.g. after
    a restart. time_frame=6m so postings from older searches are still found.
    Returns (job_dict_or_None, error)."""
    jobs, error = _request_active_jobs(
        {"id": job_id, "time_frame": "6m", "limit": 1}
    )
    return (jobs[0] if jobs else None), error


def _job_salary_text(job: dict, missing: str = "Not specified") -> str:
    """Build a salary string from a job record: prefer the AI-extracted range,
    fall back to the raw `salary` field, else `missing`. Shared by the search
    formatter and write_job_blog so both render pay the same way."""
    cur = job.get("ai_salary_currency") or ""
    lo = job.get("ai_salary_min_value")
    hi = job.get("ai_salary_max_value")
    single = job.get("ai_salary_value")
    unit = job.get("ai_salary_unit_text") or ""
    per = f" / {unit.lower()}" if unit else ""

    if lo and hi:
        return f"{cur} {lo} - {hi}{per}".strip()
    if single:
        return f"{cur} {single}{per}".strip()
    raw = job.get("salary")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return missing


def _format_active_job(i: int, job: dict) -> str:
    """Render one Active ATS job record into a detailed, scannable block,
    surfacing every useful field this API provides. Note: this data source has
    NO full description text and NO employer reviews/ratings — the closest it
    offers are the AI responsibility/requirements summaries shown below."""
    title = job.get("title", "Unknown role")
    org = job.get("organization", "Unknown company")

    locs = job.get("locations_derived") or job.get("locations_alt") or []
    loc = locs[0] if locs else "N/A"

    # Work arrangement: "On-site" / "Hybrid" / "Remote" (+ office days if known).
    arrangement = job.get("ai_work_arrangement") or "N/A"
    office_days = job.get("ai_work_arrangement_office_days")
    if office_days:
        arrangement += f" ({office_days} office days)"

    employment = ", ".join(
        job.get("employment_type") or job.get("ai_employment_type") or []
    ) or "N/A"
    posted = (job.get("date_posted") or "N/A").replace("T", " ")
    valid_through = (job.get("date_valid_through") or "").replace("T", " ")

    salary = _job_salary_text(job)
    exp = job.get("ai_experience_level") or ""
    hours = job.get("ai_working_hours")
    visa = job.get("ai_visa_sponsorship")
    education = ", ".join(job.get("ai_education") or [])

    skills = job.get("ai_key_skills") or []
    responsibilities = (job.get("ai_core_responsibilities") or "").strip()
    requirements = (job.get("ai_requirements_summary") or "").strip()
    benefits = job.get("ai_benefits") or []

    link = job.get("url", "N/A")
    source = job.get("source") or job.get("source_type") or ""
    website = job.get("domain_derived") or ""
    linkedin_slug = job.get("org_linkedin_slug") or ""
    jid = job.get("id")

    out = [f"{i}. {title} — {org}"]
    out.append(f"   Location: {loc} | Work mode: {arrangement} | {employment}")

    line3 = [f"Posted: {posted}"]
    if valid_through:
        line3.append(f"Apply by: {valid_through}")
    if source:
        line3.append(f"via {source}")
    out.append("   " + " | ".join(line3))

    line4 = [f"Salary: {salary}"]
    if exp:
        line4.append(f"Experience: {exp} yrs")
    if hours:
        line4.append(f"Hours: {hours}/week")
    line4.append(f"Visa sponsorship: {'Yes' if visa else 'No'}")
    out.append("   " + " | ".join(line4))

    if education:
        out.append(f"   Education: {education}")
    if skills:
        out.append(f"   Skills: {', '.join(skills[:10])}")
    if responsibilities:
        out.append(f"   Role summary: {responsibilities}")
    if requirements:
        out.append(f"   Requirements: {requirements}")
    if benefits:
        out.append(f"   Benefits: {', '.join(benefits[:6])}")

    company_bits = []
    if website:
        company_bits.append(f"https://{website}")
    if linkedin_slug:
        company_bits.append(f"https://www.linkedin.com/company/{linkedin_slug}")
    if company_bits:
        out.append(f"   Company: {' | '.join(company_bits)}")

    # The Job ID is what write_job_blog(job_id=...) expects — keep it visible
    # right next to the apply link so the model (and user) can reference it.
    out.append(f"   Job ID: {jid if jid is not None else 'N/A'} | Apply: {link}")
    return "\n".join(out)


@tool
def search_jobs(
    title: str,
    location: str = "india",
    time_frame: str = "24h",
    limit: int = 2,
    offset: int = 0,
) -> str:
    """Search recent job listings pulled directly from company ATS boards
    (Greenhouse, Oracle Cloud, Workday, Lever, etc.).
    Use this when the user wants to find jobs, openings, vacancies, or
    work-from-home roles. Each result is already detailed (skills, experience,
    requirements summary) and includes a direct apply link, so no follow-up
    details call is needed. Each result also shows a numeric Job ID — pass
    that Job ID to write_job_blog to write a blog about that exact posting.

    title: job title keywords only, e.g. "software engineer" — do NOT put the
           location in here.
    location: country, state, or city name, e.g. "india", "kolkata".
    time_frame: how recent the postings are, e.g. "24h", "7d".
    limit: max number of jobs to return (default 2).
    offset: pagination offset — pass 10, 20, ... to get the next pages."""

    jobs, error = _fetch_active_jobs(title, location, time_frame, limit, offset)

    if not jobs:
        if error:
            return f"Job search failed: {error}"
        return f"No jobs found for '{title}' in '{location}' (last {time_frame})."

    # Cache every record by its API id so write_job_blog(job_id=...) can blog
    # the EXACT posting the user saw — no re-search, no wrong-job drift.
    for job in jobs:
        jid = job.get("id")
        if jid is not None:
            try:
                LAST_JOBS[int(jid)] = job
            except (TypeError, ValueError):
                pass

    lines = [
        _format_active_job(i, job) for i, job in enumerate(jobs, start=offset + 1)
    ]
    header = (
        f"Found {len(jobs)} jobs for '{title}' in '{location}' "
        f"(posted within {time_frame}):\n\n"
    )
    return header + "\n\n".join(lines)


# def _fetch_job_details(job_id, country):
#     """Fetch raw job-details dicts for one or more (comma-separated) Job IDs.
#     Returns (jobs_list, error). The endpoint 500s on a country mismatch and can
#     fail transiently, so we try with the country then fall back to omitting it.
#     Shared by get_job_details and write_job_blog."""
#     api_key = os.getenv("JSEARCH_API_KEY")
#     if not api_key:
#         return [], "JSEARCH_API_KEY is not set"

#     url = "https://api.openwebninja.com/jsearch/job-details"
#     headers = {"x-api-key": api_key}
#     attempts = [{"job_id": job_id, "country": country}, {"job_id": job_id}]
#     last_error = None
#     for params in attempts:
#         try:
#             response = requests.get(url, headers=headers, params=params, timeout=30)
#             response.raise_for_status()
#             data = response.json()
#             jobs = [j for j in (data.get("data") or []) if isinstance(j, dict)]
#             return jobs, None
#         except Exception as e:
#             last_error = e
#     return [], last_error


# @tool
# def get_job_details(job_id: str, country: str = "in") -> str:
#     """Get the full details of a specific job using its Job ID.
#     Call this after search_jobs when the user wants to know more about a
#     particular job: full description, qualifications, responsibilities,
#     benefits, salary range, employer reviews, and how to apply.

#     job_id: the Job ID returned by search_jobs. Up to 20 comma-separated IDs
#             are supported (each counts as one request).
#     country: two-letter ISO code. Use the SAME country you searched with, as a
#              mismatch can make this endpoint fail."""

#     jobs, error = _fetch_job_details(job_id, country)
#     if not jobs:
#         if error:
#             return f"Failed to fetch job details: {error}"
#         return f"No details found for job_id '{job_id}'."

#     return "\n\n" + ("\n\n" + ("=" * 40) + "\n\n").join(
#         _format_job_detail(job) for job in jobs
#     )


# @tool
# def get_estimated_salary(
#     job_title: str,
#     location: str,
#     location_type: str = "ANY",
#     years_of_experience: str = "ALL",
# ) -> str:
#     """Get the estimated salary / pay for a job title at a location.
#     Use this when the user asks how much a role pays, the salary range, or the
#     expected compensation for a kind of job somewhere (no specific company).
#     The currency in the result follows the location (e.g. INR for India).

#     job_title: e.g. "nodejs developer", "data analyst".
#     location: e.g. "new york", "kolkata, india", "India".
#     location_type: one of ANY, CITY, STATE, COUNTRY. For a whole country such as
#                    "India", set this to COUNTRY so it is not mismatched to a
#                    similarly named city (e.g. Indianapolis).
#     years_of_experience: one of ALL, LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX,
#                          SEVEN_TO_NINE, TEN_TO_FOURTEEN, ABOVE_FIFTEEN."""

#     api_key = os.getenv("JSEARCH_API_KEY")
#     if not api_key:
#         return "Salary estimation is unavailable: JSEARCH_API_KEY is not set."

#     url = "https://api.openwebninja.com/jsearch/estimated-salary"
#     headers = {"x-api-key": api_key}
#     params = {
#         "job_title": job_title,
#         "location": location,
#         "location_type": location_type,
#         "years_of_experience": years_of_experience,
#     }

#     try:
#         response = requests.get(url, headers=headers, params=params, timeout=30)
#         response.raise_for_status()
#         data = response.json()
#     except Exception as e:
#         return f"Salary estimation failed: {e}"

#     estimates = data.get("data", []) or []
#     if not estimates:
#         return f"No salary data found for '{job_title}' in '{location}'."

#     return "\n\n".join(_format_salary(est) for est in estimates)


# @tool
# def get_company_salary(
#     company: str,
#     job_title: str,
#     location: str = "",
#     location_type: str = "ANY",
#     years_of_experience: str = "ALL",
# ) -> str:
#     """Get the estimated pay for a job title at a SPECIFIC named company.
#     Use this when the user asks how much a role pays at a particular employer,
#     e.g. "how much does a software developer make at Amazon?".
#     The currency in the result follows the location (e.g. INR for India).

#     company: the employer name, e.g. "Amazon", "Google".
#     job_title: e.g. "software developer", "data scientist".
#     location: optional free-text area, e.g. "seattle", "India". Leave empty for
#               a company-wide estimate.
#     location_type: one of ANY, CITY, STATE, COUNTRY. For a whole country such as
#                    "India", set this to COUNTRY so it is not mismatched to a
#                    similarly named city (e.g. Indianapolis).
#     years_of_experience: one of ALL, LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX,
#                          SEVEN_TO_NINE, TEN_TO_FOURTEEN, ABOVE_FIFTEEN."""

#     api_key = os.getenv("JSEARCH_API_KEY")
#     if not api_key:
#         return "Salary estimation is unavailable: JSEARCH_API_KEY is not set."

#     url = "https://api.openwebninja.com/jsearch/company-job-salary"
#     headers = {"x-api-key": api_key}
#     params = {
#         "company": company,
#         "job_title": job_title,
#         "location_type": location_type,
#         "years_of_experience": years_of_experience,
#     }
#     if location:
#         params["location"] = location

#     try:
#         response = requests.get(url, headers=headers, params=params, timeout=30)
#         response.raise_for_status()
#         data = response.json()
#     except Exception as e:
#         return f"Salary estimation failed: {e}"

#     estimates = data.get("data", []) or []
#     if not estimates:
#         return f"No salary data found for '{job_title}' at '{company}'."

#     return "\n\n".join(_format_salary(est) for est in estimates)


# ─── Gemini (Google AI Studio) — used only to WRITE blog prose ──────────────
# The blog text is written by Gemini, while the job FACTS still come from the
# Active ATS API (so the post can't invent salaries, links, or requirements).
# Model / timeout / retry policy are env-configurable.

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "60000"))
GEMINI_MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))

# SEO quality gate: after the blog is written, a second Gemini call audits it
# and returns a 0-100 SEO score. Drafts below SEO_MIN_SCORE are rewritten with
# the auditor's issues fed back in, up to SEO_MAX_IMPROVE_ROUNDS times.
SEO_MIN_SCORE = int(os.getenv("SEO_MIN_SCORE", "90"))
SEO_MAX_IMPROVE_ROUNDS = int(os.getenv("SEO_MAX_IMPROVE_ROUNDS", "3"))

# The Google Jobs JSON-LD schema is generated in the background and written to
# this folder (one .html file per blog) instead of cluttering the chat output.
BLOG_OUTPUT_DIR = os.getenv("BLOG_OUTPUT_DIR", "blog_output")

# Auto-cleanup so schema files don't pile up: every time a new one is written,
# older schema files are purged — anything beyond SCHEMA_MAX_FILES newest, or
# older than SCHEMA_MAX_AGE_DAYS, is deleted (the file just written is always
# kept). Set SCHEMA_MAX_FILES=1 to keep ONLY the latest blog's schema.
SCHEMA_MAX_FILES = int(os.getenv("SCHEMA_MAX_FILES", "20"))
SCHEMA_MAX_AGE_DAYS = float(os.getenv("SCHEMA_MAX_AGE_DAYS", "7"))


def _cleanup_schema_files(keep_path: str | None = None) -> int:
    """Purge old schema_*.html files from BLOG_OUTPUT_DIR. The file at
    keep_path (the one just written) is never deleted. Of the rest, newest
    first, a file is removed if it would push the folder past SCHEMA_MAX_FILES
    total or if it is older than SCHEMA_MAX_AGE_DAYS. Returns how many files
    were deleted. Failures are logged, never raised — cleanup must not break
    blog generation."""
    try:
        entries = []
        for name in os.listdir(BLOG_OUTPUT_DIR):
            if not (name.startswith("schema_") and name.endswith(".html")):
                continue  # never touch anything else in the folder
            path = os.path.join(BLOG_OUTPUT_DIR, name)
            if keep_path and os.path.abspath(path) == os.path.abspath(keep_path):
                continue
            entries.append((os.path.getmtime(path), path))
    except OSError as e:
        logger.debug("schema cleanup: could not list %s: %s", BLOG_OUTPUT_DIR, e)
        return 0

    entries.sort(reverse=True)  # newest first
    cutoff = time.time() - SCHEMA_MAX_AGE_DAYS * 86400
    # keep_path already occupies one slot, so older files get MAX_FILES - 1.
    keep_others = max(0, SCHEMA_MAX_FILES - 1)

    removed = 0
    for idx, (mtime, path) in enumerate(entries):
        if idx >= keep_others or mtime < cutoff:
            try:
                os.remove(path)
                removed += 1
            except OSError as e:
                logger.debug("schema cleanup: could not delete %s: %s", path, e)
    return removed


def _gemini_generate(system_text: str, user_text: str, temperature: float = 0.7):
    """Call Gemini once to turn a grounded prompt into prose.
    Returns (text, error): on success error is None; on failure text is None and
    error is a short human-readable string. Retries transient 5xx / 429 errors
    with exponential backoff; a bad key (401/403) and other 4xx fail fast.
    temperature: 0.7 default for creative blog prose; pass a low value (e.g.
    0.2) for judge/auditor calls that must be consistent and parseable."""
    api_key = os.getenv("GOOGLE_AI_STUDIO_API_KEY")
    if not api_key:
        return None, "GOOGLE_AI_STUDIO_API_KEY is not set"

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )

    last_error = None
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_text,
                    temperature=temperature,
                    max_output_tokens=4096,
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text, None
            last_error = "Gemini returned no content (possibly filtered)"
        except genai_errors.ClientError as e:
            code = getattr(e, "code", None)
            if code in (401, 403):
                return None, "the Google API key was rejected (check GOOGLE_AI_STUDIO_API_KEY)"
            last_error = e
            if code != 429:  # non-retryable client error
                return None, f"Gemini request failed: {e}"
        except genai_errors.ServerError as e:
            last_error = e  # retryable
        except Exception as e:
            return None, f"unexpected Gemini error: {e}"

        if attempt < GEMINI_MAX_ATTEMPTS:
            wait = 1.5 * (2 ** (attempt - 1))
            logger.debug("Gemini transient error, retrying in %.1fs: %s", wait, last_error)
            time.sleep(wait)

    return None, f"Gemini failed after {GEMINI_MAX_ATTEMPTS} attempts: {last_error}"


def _job_posting_schema(job: dict) -> str:
    """Build Google's JobPosting JSON-LD schema for one job, entirely in Python
    from the API record — never via the writer model, so it can't hallucinate
    identifiers, dates, or salaries. Fields that aren't in the data are simply
    OMITTED (Google prefers a missing field over an invented one). Returns a
    ready-to-paste <script type="application/ld+json"> block; this is the key
    ingredient for appearing in the Google Jobs widget."""
    org = job.get("organization") or ""
    title = job.get("title") or ""
    website = job.get("domain_derived") or ""
    responsibilities = (job.get("ai_core_responsibilities") or "").strip()
    requirements = (job.get("ai_requirements_summary") or "").strip()
    description = " ".join(p for p in (responsibilities, requirements) if p) \
        or f"{title} role at {org}."

    schema = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": title,
        "description": description,
    }

    posted = (job.get("date_posted") or "").split("T")[0]
    if posted:
        schema["datePosted"] = posted
    valid_through = (job.get("date_valid_through") or "").split("T")[0]
    if valid_through:  # only if the posting really has a deadline
        schema["validThrough"] = valid_through

    emp = job.get("employment_type") or job.get("ai_employment_type") or []
    if emp:
        schema["employmentType"] = emp[0] if len(emp) == 1 else list(emp)

    if job.get("id") is not None:
        # Real, stable identifier: the ATS feed's own job id.
        schema["identifier"] = {
            "@type": "PropertyValue",
            "name": org,
            "value": str(job["id"]),
        }

    hiring_org = {"@type": "Organization", "name": org}
    if website:
        hiring_org["sameAs"] = f"https://{website}"
    logo = job.get("org_logo_permalink")
    if logo:
        hiring_org["logo"] = logo
    schema["hiringOrganization"] = hiring_org

    locs = job.get("locations_derived") or job.get("locations_alt") or []
    loc = str(locs[0]) if locs else ""
    if loc:
        address = {"@type": "PostalAddress", "addressLocality": loc}
        if "india" in loc.lower():
            address["addressCountry"] = "IN"
        schema["jobLocation"] = {"@type": "Place", "address": address}

    arrangement = (job.get("ai_work_arrangement") or "").lower()
    if "remote" in arrangement:
        schema["jobLocationType"] = "TELECOMMUTE"
        schema["applicantLocationRequirements"] = {
            "@type": "Country",
            "name": "India" if (not loc or "india" in loc.lower()) else loc,
        }

    cur = job.get("ai_salary_currency")
    lo = job.get("ai_salary_min_value")
    hi = job.get("ai_salary_max_value")
    single = job.get("ai_salary_value")
    unit = (job.get("ai_salary_unit_text") or "YEAR").upper()
    if cur and (single or (lo and hi)):
        value = {"@type": "QuantitativeValue", "unitText": unit}
        if lo and hi:
            value["minValue"] = lo
            value["maxValue"] = hi
        else:
            value["value"] = single
        schema["baseSalary"] = {
            "@type": "MonetaryAmount",
            "currency": cur,
            "value": value,
        }

    if job.get("url"):
        schema["directApply"] = True

    return (
        '<script type="application/ld+json">\n'
        + json.dumps(schema, indent=2, ensure_ascii=False)
        + "\n</script>"
    )


def _seo_score_blog(blog: str, keywords: list, topic: str):
    """Audit the blog's SEO with a low-temperature Gemini call. Returns
    (score, issues): score is an int 0-100, or None if the audit call failed
    or its answer couldn't be parsed (callers should then SKIP the improvement
    loop rather than rewrite blindly); issues is a list of specific, fixable
    problem strings to feed back into a rewrite."""
    system_text = (
        "You are a strict SEO auditor for job-posting blog articles targeting "
        "Google Search in India. Score the article 0-100 against this rubric: "
        "SEO title & meta description quality (length, keyword placement, call "
        "to action); keyword usage and natural placement of the target "
        "keywords; heading structure and scannability; local SEO signals for "
        "Indian job seekers; presence and quality of an FAQ section; "
        "readability and sentence length; a clear call to action with the "
        "application link; image alt text.\n\n"
        "LOCKED BY DESIGN — treat all of these as already correct; do NOT "
        "deduct points for them and do NOT raise issues about them:\n"
        "- The fixed house template: UPPERCASE plain-text section headers, "
        "'\u2022' bullets, no markdown formatting.\n"
        f"- The URL slug format company-role-recruitment-<year> (the year is "
        "intentional; never suggest removing it).\n"
        "- Factual values copied from the source posting: salary (which may "
        "legitimately read 'Best in Industry' when pay is not disclosed), "
        "apply links, dates, experience, and company details.\n"
        "- Technical SEO: a valid JobPosting JSON-LD schema block is generated "
        "separately and attached to the page, so structured data is covered.\n\n"
        "Only raise issues that a PROSE rewrite within those constraints could "
        "actually fix (keyword placement, phrasing, sentence length, paragraph "
        "breaks, FAQ wording, call-to-action strength, local-SEO mentions). "
        "If the article is strong within its constraints, score it 90+.\n"
        "Respond with ONLY a JSON object — no markdown fences, no prose:\n"
        '{"score": <integer 0-100>, "issues": ["<specific fixable issue>", ...]}\n'
        "List at most 8 issues, each concrete enough that a writer could fix "
        "it directly."
    )
    user_text = (
        f"Target topic: {topic}\n"
        f"Target keywords: {', '.join(keywords) if keywords else 'None provided'}\n\n"
        f"ARTICLE:\n{blog}"
    )
    text, error = _gemini_generate(system_text, user_text, temperature=0.2)
    if text is None:
        return None, [error or "SEO audit call failed"]

    clean = re.sub(r"```(?:json)?", "", text).strip()
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else clean)
        score = max(0, min(100, int(data.get("score"))))
        issues = [str(i) for i in (data.get("issues") or [])][:8]
        return score, issues
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return None, ["could not parse the SEO audit response"]


def _seo_precheck(blog: str, jobs: list, year: int) -> list:
    """Deterministic, zero-cost SEO checklist run in plain Python alongside
    the Gemini audit. It catches the objective problems an LLM judge scores
    inconsistently: metadata lengths, slug format, missing sections, the
    job's own city for local SEO, over-long bullet runs, and the salary
    search phrase for undisclosed pay. Returns a list of specific issue
    strings (empty = checklist passes); these are merged with the auditor's
    issues to drive the automatic rewrite loop."""
    issues = []
    lines = blog.splitlines()

    def _meta_value(prefix):
        """Value of a 'Prefix: value' line in the top metadata block, or None."""
        for ln in lines[:8]:
            if ln.strip().lower().startswith(prefix.lower()):
                return ln.split(":", 1)[1].strip() if ":" in ln else ""
        return None

    title = _meta_value("SEO title")
    if title is None:
        issues.append("the first line must be 'SEO title: ...'")
    elif len(title) > 60:
        issues.append(f"the SEO title is {len(title)} characters — shorten it to 60 or fewer")

    meta = _meta_value("Meta description")
    if meta is None:
        issues.append("a 'Meta description: ...' line is missing from the top metadata")
    elif not (130 <= len(meta) <= 165):
        issues.append(
            f"the meta description is {len(meta)} characters — rewrite it to 150-160 "
            "characters covering the role, company, location and a direct call to apply"
        )

    slug = _meta_value("Suggested URL Slug")
    if slug is None:
        issues.append("a 'Suggested URL Slug: ...' line is missing from the top metadata")
    else:
        if len(slug) > 60:
            issues.append(f"the URL slug is {len(slug)} characters — shorten it to 60 or fewer")
        if f"recruitment-{year}" not in slug:
            issues.append(f"the URL slug must contain 'recruitment-{year}'")
        if slug and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
            issues.append("the URL slug must be lowercase words separated by single hyphens")

    if _meta_value("Image Alt Text") is None:
        issues.append("an 'Image Alt Text: ...' line is missing from the top metadata")

    low = blog.lower()
    if "frequently asked questions" not in low:
        issues.append("the FREQUENTLY ASKED QUESTIONS (FAQs) section is missing")
    if f"recruitment {year}" not in low:
        issues.append(f"the keyword 'Recruitment {year}' never appears in the body")

    # Local SEO: the job's own city (first part of its location) must appear.
    for job in jobs:
        locs = job.get("locations_derived") or job.get("locations_alt") or []
        loc = str(locs[0]) if locs else ""
        city = loc.split(",")[0].strip()
        if city and city.lower() != "india" and city.lower() not in low:
            issues.append(
                f"the job's own city '{city}' is never mentioned — weave it into the intro, "
                "meta description or FAQ for local SEO"
            )

    # Readability: flag any run of more than 9 consecutive bullet lines.
    # A bullet ending with ':' is a sub-group label (e.g. '• DevOps & Automation:')
    # — it RESETS the counter, so a long list that is already properly grouped
    # into labelled sub-sections is not flagged as one giant run.
    run = longest = 0
    for ln in lines:
        stripped = ln.strip()
        if re.match(r"^[\u2022*-]\s", stripped):
            if stripped.rstrip().endswith(":"):
                run = 0  # labelled sub-group header — starts a new, short run
            else:
                run += 1
                longest = max(longest, run)
        else:
            run = 0
    if longest > 9:
        issues.append(
            f"one bulleted list runs {longest} bullets long — split it into 2-3 short "
            "labelled sub-groups (e.g. 'Programming & Frameworks', 'Testing & Automation', "
            "'Cloud & DevOps') to keep readers on the page"
        )

    # Salary search phrase: when pay is undisclosed, the post should still
    # carry a 'competitive <role> salary in <place>' phrase for search volume
    # (a phrase, never an invented number).
    if "best in industry" in low and not re.search(r"competitive[^.\n]{0,80}salary", low):
        issues.append(
            "salary is undisclosed ('Best in Industry') — add one sentence with the "
            "search-friendly phrase 'competitive <role> salary in <city or India>' "
            "(a phrase only, no invented numbers)"
        )

    return issues


def _is_walkin_job(job: dict) -> bool:
    """Best-effort walk-in drive detection. The Active ATS API has no explicit
    walk-in field, so this scans the posting's own text (title + AI summaries)
    for 'walk-in' / 'walk in' wording. Drives the conditional DOCUMENTS TO
    CARRY section: candidates only need physical documents when they attend
    in person, not for an online application."""
    parts = [
        job.get("title") or "",
        job.get("ai_core_responsibilities") or "",
        job.get("ai_requirements_summary") or "",
        " ".join(job.get("ai_key_skills") or []),
    ]
    text = " ".join(parts).lower()
    return bool(re.search(r"walk[\s-]?in", text))


def _blog_grounding_problems(blog: str, jobs: list) -> list:
    """Cheap post-generation grounding check: for every featured job, the blog
    must mention the company name and contain the exact official apply link.
    Returns a list of human-readable problem strings (empty = all good). This
    is what catches the failure mode where the writer model drifts off and
    blogs a completely different job."""
    problems = []
    low = blog.lower()
    for job in jobs:
        company = (job.get("organization") or "").strip()
        link = (job.get("url") or "").strip()
        if company and company.lower() not in low:
            problems.append(f"the blog never mentions the company '{company}'")
        if link and link not in blog:
            problems.append(f"the exact apply link {link} is missing from the blog")
    return problems


@tool
def write_job_blog(
    job_id: int = 0,
    title: str = "",
    location: str = "india",
    time_frame: str = "7d",
    max_results: int = 10,
) -> str:
    """Write a professional, SEO-optimized, ready-to-publish blog post for an Indian job portal.
    Uses Google Gemini to transform job data into a high-ranking career article.
    Job facts come straight from the Active ATS job records, so the post can't
    invent salaries, links, or requirements.

    TWO MODES:
    1. Specific posting — pass job_id (the numeric Job ID shown next to a
       result from search_jobs). The blog features EXACTLY that job; do not
       pass title in this mode. Use this whenever the user picks one job from
       results already shown.
    2. General roundup — leave job_id at 0 and pass title keywords (e.g.
       "software engineer") + location. Featured jobs are pulled fresh from
       the job search source.

    job_id: the numeric Job ID of one specific posting from search_jobs results.
    title: job title keywords to feature (roundup mode only).
    location: country, state, or city name, e.g. "india", "kolkata".
    time_frame: how recent the postings should be, e.g. "24h", "7d".
    max_results: how many jobs to feature in the main body (roundup mode)."""

    error = None

    if job_id:
        # ── Mode 1: one specific posting, by the API's internal id ────────
        try:
            job_id = int(job_id)
        except (TypeError, ValueError):
            return f"'{job_id}' is not a valid numeric Job ID."

        job = LAST_JOBS.get(job_id)
        if job is None:
            # Not in this session's cache (e.g. after a restart) — the API
            # supports fetching a single job by id, so recover that way.
            job, error = _fetch_job_by_id(job_id)
        if job is None:
            hint = f" ({error})" if error else ""
            return (
                f"I couldn't find a job with Job ID {job_id}{hint}. "
                "Run search_jobs first and use the numeric Job ID shown "
                "next to the result you want to blog about."
            )

        featured_jobs = [job]
        # Other cached postings from this session's searches become the
        # Related Jobs section — no extra API call needed.
        related_jobs = [j for jid, j in LAST_JOBS.items() if jid != job_id][:8]
        topic = f"{job.get('title', 'job')} at {job.get('organization', 'the company')}"
    else:
        # ── Mode 2: general roundup by title keywords ─────────────────────
        if not title:
            return (
                "Please provide either the Job ID of a specific posting "
                "(from search_jobs results) or job title keywords for a "
                "general roundup blog."
            )
        # Fetch a few extra results so the surplus can serve as Related Jobs
        # without a second API call.
        want = max_results + 8
        all_jobs, error = _fetch_active_jobs(title, location, time_frame, want, 0)
        featured_jobs = all_jobs[:max_results]
        related_jobs = all_jobs[max_results:]
        topic = f"{title} jobs in {location}"

        if not featured_jobs:
            if error:
                return f"Could not fetch job data to write the blog: {error}"
            return f"No jobs found for '{topic}', so there is nothing to write about."

    # ── Grounded data for the FEATURED job(s) ────────────────────────────
    # Note: this API provides NO full description text and NO employer
    # reviews/ratings. The description is grounded in the AI responsibility +
    # requirements summaries, and the prompt below forbids inventing reviews.
    blocks = []
    all_seo_keywords = []
    walkin_flags = []
    for job in featured_jobs:
        job_title = job.get("title", "N/A")
        company = job.get("organization", "N/A")
        locs = job.get("locations_derived") or job.get("locations_alt") or []
        loc = locs[0] if locs else "India"

        salary = _job_salary_text(job, missing="Best in Industry")

        exp = job.get("ai_experience_level") or ""
        exp_str = f"{exp} years" if exp else "Not specified (Check description)"

        arrangement = job.get("ai_work_arrangement") or "Not specified"
        office_days = job.get("ai_work_arrangement_office_days")
        if office_days:
            arrangement += f" ({office_days} office days)"

        hours = job.get("ai_working_hours")
        visa = job.get("ai_visa_sponsorship")
        education = ", ".join(job.get("ai_education") or []) or "As per Company Norms"

        skills = job.get("ai_key_skills") or []
        responsibilities = (job.get("ai_core_responsibilities") or "").strip()
        requirements = (job.get("ai_requirements_summary") or "").strip()
        benefits = job.get("ai_benefits") or []
        keywords = job.get("ai_keywords") or []
        all_seo_keywords.extend(keywords[:10])

        # ── New job-seeker-helpful fields ─────────────────────────────────
        employment = ", ".join(
            job.get("employment_type") or job.get("ai_employment_type") or []
        ) or "As per Company Norms"
        posted = (job.get("date_posted") or "").split("T")[0]
        deadline = (job.get("date_valid_through") or "").split("T")[0]
        walkin = _is_walkin_job(job)
        walkin_flags.append(walkin)

        # Organization details (present when include_basic_organization_details
        # is on and the org is tracked) — ground the ABOUT THE COMPANY section.
        org_industry = job.get("org_linkedin_industry") or ""
        org_hq = job.get("org_linkedin_headquarters") or ""
        org_size = job.get("org_linkedin_size") or job.get("org_linkedin_headcount") or ""
        org_founded = job.get("org_linkedin_founded_date") or ""
        org_about = (
            job.get("org_linkedin_description") or job.get("org_linkedin_slogan") or ""
        ).strip()
        if len(org_about) > 500:
            org_about = org_about[:500].rstrip() + " ..."
        org_specialties = job.get("org_linkedin_specialties") or ""
        if isinstance(org_specialties, list):
            org_specialties = ", ".join(str(s) for s in org_specialties)
        is_agency = job.get("org_linkedin_recruitment_agency_derived")

        website = job.get("domain_derived") or ""
        linkedin_slug = job.get("org_linkedin_slug") or ""
        official_link = job.get("url", "")

        fields = [
            f"Title: {job_title}",
            f"Company: {company}",
            f"CompanyWebsite: {('https://' + website) if website else 'Not available'}",
            f"CompanyLinkedIn: {('https://www.linkedin.com/company/' + linkedin_slug) if linkedin_slug else 'Not available'}",
            f"CompanyIndustry: {org_industry or 'Not available'}",
            f"CompanyHeadquarters: {org_hq or 'Not available'}",
            f"CompanySize: {str(org_size) + ' employees' if org_size else 'Not available'}",
            f"CompanyFounded: {org_founded or 'Not available'}",
            f"CompanyAbout: {org_about or 'Not available'}",
            f"CompanySpecialties: {org_specialties or 'Not available'}",
            f"PostedViaRecruitmentAgency: {'Yes' if is_agency else 'No'}",
            f"Location: {loc}",
            f"WorkMode: {arrangement}",
            f"EmploymentType: {employment}",
            f"ApplicationMode: {'Walk-in Drive' if walkin else 'Online Application'}",
            f"DatePosted: {posted or 'Not specified'}",
            f"LastDateToApply: {deadline or 'Not specified — apply as early as possible'}",
            f"Salary: {salary}",
            f"Experience: {exp_str}",
            f"WorkingHours: {str(hours) + ' per week' if hours else 'As per Company Norms'}",
            f"VisaSponsorship: {'Yes' if visa else 'No'}",
            f"Education: {education}",
            f"KeySkills: {', '.join(skills[:12]) if skills else 'Not specified'}",
            f"RoleResponsibilities: {responsibilities or 'Not specified'}",
            f"RequirementsSummary: {requirements or 'Not specified'}",
            f"Benefits: {', '.join(benefits) if benefits else 'As per Company Norms'}",
            f"OfficialApplyLink: {official_link}",
        ]
        blocks.append("\n".join(fields))

    job_data = ("\n\n" + ("-" * 20) + "\n\n").join(blocks)

    # ── Grounded data for the RELATED JOBS section ───────────────────────
    related_lines = []
    for j in related_jobs:
        r_title = (j.get("title") or "").strip()
        r_company = (j.get("organization") or "").strip()
        r_link = j.get("url", "")
        if r_title and r_link:
            related_lines.append(f"• {r_title} — {r_company}: {r_link}")
    related_data = "\n".join(related_lines) if related_lines else "NONE"

    # Deduplicate the AI keywords from the postings, preserving order — these
    # become grounded SEO keywords for the article.
    seen = set()
    seo_keywords = [
        k for k in all_seo_keywords if not (k.lower() in seen or seen.add(k.lower()))
    ][:15]

    year = datetime.now().year
    any_walkin = any(walkin_flags)

    # ── Section template, assembled dynamically ──────────────────────────
    # DOCUMENTS TO CARRY only makes sense for a WALK-IN DRIVE (candidates
    # physically attend and must bring papers). For a normal online
    # application the section is omitted from the template entirely — decided
    # here in Python, not left to the writer model — and the section
    # numbering below adjusts automatically.
    template_sections = [
        f"MAIN TITLE (uppercase): <ROLE NAME> RECRUITMENT {year} AT <COMPANY NAME>, "
        "immediately followed on the next line by an image placeholder in exactly this format: "
        f"(Add Image Here - Alt Text: <Company> Recruitment {year} <Role> <Location>)",

        "Intro paragraph (no header): 4-6 sentences hooking the reader \u2014 name the company "
        "and what it does (infer only from the job data), the role, the location, the "
        f"experience needed, and end with a call to explore this Latest Job Vacancy / Recruitment {year}.",

        "JOB OVERVIEW TABLE \u2014 exactly these labelled lines:\n"
        "   Company Name: ...\n"
        "   Job Role: ...\n"
        "   Salary: <the Salary value from Job Data>\n"
        "   Location: <Location> (<WorkMode>)\n"
        "   Employment Type: <EmploymentType>\n"
        "   Eligibility: <from Education, else 'As per Company Norms'>\n"
        "   Experience Required: <Experience>\n"
        "   Posted On: <DatePosted>\n"
        "   Last Date to Apply: <LastDateToApply>\n"
        "   Application Mode: <ApplicationMode>",

        "ABOUT THE COMPANY \u2014 3-5 sentences introducing the employer, built ONLY from "
        "CompanyAbout, CompanyIndustry, CompanyHeadquarters, CompanySize, CompanyFounded and "
        "CompanySpecialties in the Job Data. If ALL of those are 'Not available', write ONE "
        "sentence saying detailed company information is not available and point readers to "
        "the CompanyWebsite instead. If PostedViaRecruitmentAgency is Yes, add one sentence "
        "noting the posting is via a staffing/recruitment agency, so the final employer may "
        "differ from the poster.",

        "JOB ROLE & RESPONSIBILITIES \u2014 one intro sentence ('As a <role> at <company>, you "
        "will...'), then 6-9 bullet points built from RoleResponsibilities and KeySkills. Keep "
        "each bullet under ~20 words so the list stays scannable.",

        "ELIGIBILITY CRITERIA \u2014 four labelled sub-parts, each starting with a bullet:\n"
        "   \u2022 Education: ...\n"
        "   \u2022 Experience: ...\n"
        "   \u2022 Technical Skills: followed by nested bullets drawn from KeySkills and "
        "RequirementsSummary. When there are more than 6 skills, group them under 2-3 short "
        "labelled sub-headings appropriate to the role (e.g. 'Programming & Frameworks', "
        "'Testing & Automation', 'Cloud & DevOps') so no single list runs long.\n"
        "   \u2022 Soft Skills: followed by 3-4 nested bullets (communication, problem-solving, "
        "collaboration, leadership as appropriate to the seniority).",

        "SALARY & BENEFITS \u2014 first state the Salary value from Job Data EXACTLY (including "
        "currency and pay period, if given) in one sentence, then bullet points listing each "
        "item from Benefits. Also mention WorkingHours and whether VisaSponsorship is offered. "
        "If Benefits is 'As per Company Norms', say the company will share compensation and "
        "perks details during the hiring process \u2014 do NOT invent any perks. If the Salary "
        "is 'Best in Industry' (undisclosed), ALSO include one search-friendly sentence using "
        "the phrase 'competitive <role> salary in <city or India>' \u2014 search engines love "
        "salary phrases \u2014 while still labelling the value as Best in Industry and NEVER "
        "inventing numeric figures.",

        "SELECTION PROCESS \u2014 one intro sentence, then 3-4 named stages, each stage name "
        "followed by a one-sentence description: Online Application & Shortlisting; Technical "
        "Assessment/Round 1; Technical Interview Rounds (2-3); HR Interview.",
    ]

    if any_walkin:
        template_sections.append(
            "DOCUMENTS TO CARRY \u2014 this posting is a WALK-IN DRIVE, so candidates must "
            "physically bring their papers: one intro sentence, then bullets: Updated Resume/CV, "
            "Government-issued Photo ID (Aadhar Card, Passport, Driver's License), Educational "
            "Certificates, Experience Letters (if applicable), Latest Salary Slips, "
            "Passport-sized Photographs."
        )

    template_sections += [
        "HOW TO APPLY \u2014 5-6 steps starting with clicking the Official Apply Link, "
        "mentioning redirection to the company's careers page, reviewing the description, "
        "filling the form, uploading the resume, and submitting."
        + (
            " Since this is a walk-in drive, also tell candidates to confirm the exact venue, "
            "date and time from the official posting before attending."
            if any_walkin else ""
        )
        + " If LastDateToApply gives a real date, remind readers to apply before that deadline.",

        "OFFICIAL APPLY LINK \u2014 exactly this format:\n"
        "   Apply Here: <OfficialApplyLink copied exactly>\n"
        "   Note: Always apply through official company portals to avoid fraud. <Company> will "
        "never ask for money or personal banking details during the recruitment process.",

        "EMPLOYER REVIEWS \u2014 2-3 sentences on the work environment based ONLY on the "
        "Benefits, WorkMode and RoleResponsibilities provided (e.g. hybrid flexibility, stock "
        "purchase plan, learning programs). Do NOT state any numeric rating. If Benefits is "
        "'As per Company Norms', say review details are not available and advise candidates to "
        "research the company on trusted review platforms.",

        "FREQUENTLY ASKED QUESTIONS (FAQs) \u2014 3-4 numbered question-and-answer pairs, "
        "answered ONLY from the Job Data: (1) is the role remote/hybrid/on-site (use WorkMode "
        "and Location), (2) what is the salary range (copy the Salary value EXACTLY), "
        "(3) what key skills and experience are required (use KeySkills and Experience), and "
        "(4) what is the application deadline or how to apply (use LastDateToApply and the "
        "Official Apply Link). Phrase each question the way an Indian job seeker would search "
        "it on Google, naming the company and role. Keep each answer 1-3 sentences.",

        "RELATED JOBS \u2014 ONLY if Related Jobs Data is not 'NONE': list each job title "
        "(with company) followed by its exact application link, copied verbatim. Do NOT add "
        "jobs that are not in the list. If Related Jobs Data is 'NONE', omit this section "
        "entirely.",
    ]

    section_template = "\n".join(
        f"{i}. {s}" for i, s in enumerate(template_sections, start=1)
    )

    system_text = (
        "Act as a Senior SEO Strategist and Job Portal Content Editor. "
        "Write a high-ranking job post blog for an Indian job seeker audience. "
        "Follow the SECTION TEMPLATE below EXACTLY — same sections, same order, "
        "same header wording.\n\n"

        "STRICT FORMATTING RULES:\n"
        "1. DO NOT use '#' for headings. Section headers must be UPPERCASE plain text "
        "exactly as written in the template (e.g. 'JOB OVERVIEW TABLE').\n"
        "2. DO NOT use '**' or '*' for bold/italics. Use plain text.\n"
        "3. Use '\u2022' for all bullet points.\n"
        "4. The blog must begin with these four lines:\n"
        f"   SEO title: <max 60 chars, include role, company and Recruitment {year}>\n"
        "   Meta description: <150-160 chars summarizing role, company, location and a call to apply>\n"
        f"   Suggested URL Slug: <SHORT lowercase-hyphenated: company-role-recruitment-{year}, "
        "max 60 characters, no city names, no filler words>\n"
        f"   Image Alt Text: <Company> Recruitment {year} - <Role> Job Poster\n\n"

        "GROUNDING RULES (CRITICAL):\n"
        "- Write ONLY about the job(s) in the Job Data below. The Title and "
        "Company in Job Data are the ONLY role and employer this blog is about "
        "— never substitute a different company, role, or posting, even one "
        "that seems similar or more familiar.\n"
        "- These values must be copied EXACTLY from Job Data, never invented or altered: "
        "Salary, OfficialApplyLink, CompanyWebsite, CompanyLinkedIn, Location, Experience, "
        "EmploymentType, ApplicationMode, DatePosted, LastDateToApply, VisaSponsorship, "
        "WorkingHours, CompanyHeadquarters, CompanySize, CompanyFounded, and every URL in "
        "Related Jobs Data.\n"
        "- NEVER invent employer ratings, review scores, or star ratings (e.g. '4.2/5') \u2014 "
        "this data source does not include review numbers.\n"
        "- Do NOT add a DOCUMENTS TO CARRY section unless it appears in the SECTION TEMPLATE "
        "below. It is only for walk-in drives; online applications never need it.\n"
        "- Responsibilities and skills MAY be reasonably elaborated with industry-standard "
        "duties and technologies, but only ones consistent with the RoleResponsibilities, "
        "RequirementsSummary and KeySkills provided.\n"
        "- If a detail is missing, write 'As per Company Norms'.\n\n"

        "SECTION TEMPLATE (in this exact order):\n"
        f"{section_template}\n\n"

        "TONE & SEO:\n"
        f"- Use keywords: 'Recruitment {year}', 'Latest Jobs in India', 'Job Vacancy', 'Latest Job Vacancy'.\n"
        "- Also weave in the SEO Keywords provided with the job data, where natural.\n"
        "- LOCAL SEO: if WorkMode is Remote or Hybrid, or Location is just 'India', naturally "
        "mention that candidates from major Indian tech hubs (Bengaluru, Hyderabad, Pune, and "
        "other cities) can apply — phrased as where CANDIDATES can be based, never as company "
        "office locations. If the job is tied to one specific city, emphasise that city and "
        "its state instead, and do NOT name other cities.\n"
        "- Confident, encouraging, professional tone aimed at Indian job seekers.\n"
    )

    user_text = (
        f"Topic: {topic}\n\n"
        f"SEO Keywords: {', '.join(seo_keywords) if seo_keywords else 'None provided'}\n\n"
        f"Job Data:\n{job_data}\n\n"
        f"Related Jobs Data:\n{related_data}"
    )

    blog, gen_error = _gemini_generate(system_text, user_text)
    if blog is None:
        return f"Failed to write the SEO blog: {gen_error}"

    # ── Post-generation grounding check ──────────────────────────────────
    # Verify the blog actually covers the requested job(s): company name
    # mentioned + exact apply link present. If not, retry ONCE with the
    # failures spelled out; a persistent wrong-company blog is rejected
    # rather than shown to the user.
    problems = _blog_grounding_problems(blog, featured_jobs)
    if problems:
        logger.debug("blog failed grounding check, retrying once: %s", problems)
        retry_user_text = user_text + (
            "\n\nYOUR PREVIOUS DRAFT FAILED THESE GROUNDING CHECKS. Rewrite the "
            "blog fixing every one of them, keeping all other rules the same:\n- "
            + "\n- ".join(problems)
        )
        retry_blog, _ = _gemini_generate(system_text, retry_user_text)
        if retry_blog and not _blog_grounding_problems(retry_blog, featured_jobs):
            blog = retry_blog
        else:
            candidate = retry_blog or blog
            remaining = _blog_grounding_problems(candidate, featured_jobs)
            if any("never mentions the company" in p for p in remaining):
                # The writer drifted to a different company/job — do not
                # publish a blog about the wrong posting.
                return (
                    "The blog generator kept drifting away from the requested "
                    "job (the company name never appeared in the draft), so I "
                    "didn't return it. Please try again in a moment."
                )
            # Only apply link(s) are missing — append them verbatim so the
            # reader always gets the official application URL.
            missing_links = [
                j.get("url") for j in featured_jobs
                if j.get("url") and j["url"] not in candidate
            ]
            if missing_links:
                candidate += "\n\nOFFICIAL APPLY LINK\n" + "\n".join(
                    f"Apply Here: {u}" for u in missing_links
                )
            blog = candidate

    # ── SEO quality gate: two layers of checking ─────────────────────────
    #   1. _seo_precheck — deterministic Python checklist (metadata lengths,
    #      slug format, FAQ present, local-SEO city, bullet-run length,
    #      salary search phrase). Objective, instant, free.
    #   2. _seo_score_blog — low-temperature Gemini audit (0-100 + issues).
    # While the score is below SEO_MIN_SCORE OR checklist items remain, the
    # blog is rewritten with BOTH sets of issues fed back in. The loop is
    # PERSISTENT: it uses every improvement round and always keeps the best
    # grounded draft so far — higher audit score wins; at an equal score the
    # draft with fewer checklist issues wins. A failed round (broken
    # grounding, unparseable audit, no improvement) just moves on to the next
    # attempt. If the very first audit call fails, the gate is skipped rather
    # than rewriting blindly.
    seo_precheck_issues = _seo_precheck(blog, featured_jobs, year)
    seo_score, seo_issues = _seo_score_blog(blog, seo_keywords, topic)
    if seo_score is not None:
        best_blog, best_score = blog, seo_score
        best_issues, best_pre = seo_issues, seo_precheck_issues
        for round_no in range(1, SEO_MAX_IMPROVE_ROUNDS + 1):
            if best_score >= SEO_MIN_SCORE and not best_pre:
                break
            combined = list(dict.fromkeys(best_pre + best_issues))[:10]
            logger.debug("SEO round %d: score %s, %d checklist issue(s): %s",
                         round_no, best_score, len(best_pre), combined)
            improve_text = user_text + (
                f"\n\nYOUR PREVIOUS DRAFT (below) SCORED {best_score}/100 in an "
                "SEO audit. Rewrite the FULL blog fixing these specific issues "
                "while keeping every rule, every section, and every factual "
                "value (salary, links, dates, company details) EXACTLY the "
                "same:\n- " + "\n- ".join(combined) +
                f"\n\nPREVIOUS DRAFT:\n{best_blog}"
            )
            improved, _ = _gemini_generate(system_text, improve_text)
            if not improved:
                continue
            improved = improved.strip()
            if _blog_grounding_problems(improved, featured_jobs):
                # Never trade facts for SEO points — discard this rewrite and
                # try again from the best grounded draft.
                logger.debug("SEO round %d: rewrite broke grounding, discarded", round_no)
                continue
            new_pre = _seo_precheck(improved, featured_jobs, year)
            new_score, new_issues = _seo_score_blog(improved, seo_keywords, topic)
            if new_score is None:
                continue
            if (new_score, -len(new_pre)) > (best_score, -len(best_pre)):
                best_blog, best_score = improved, new_score
                best_issues, best_pre = new_issues, new_pre
        blog, seo_score = best_blog, best_score
        seo_issues, seo_precheck_issues = best_issues, best_pre

    blog = _strip_markdown(blog)

    # ── Technical SEO: JobPosting JSON-LD, generated in the background ───
    # Built in Python from the API record (never by the writer model, so it
    # can't hallucinate identifiers/dates/salaries) and written to a file
    # instead of cluttering the chat output. Only if the file can't be
    # written is the schema appended inline, so it is never silently lost.
    schema_blocks = "\n".join(_job_posting_schema(j) for j in featured_jobs)
    schema_note = None
    try:
        os.makedirs(BLOG_OUTPUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        first_id = featured_jobs[0].get("id", "job")
        schema_path = os.path.join(BLOG_OUTPUT_DIR, f"schema_{first_id}_{stamp}.html")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_blocks + "\n")
        # Auto-purge older schema files so the folder never piles up; the file
        # just written is always kept (see SCHEMA_MAX_FILES / SCHEMA_MAX_AGE_DAYS).
        removed = _cleanup_schema_files(keep_path=schema_path)
        if removed:
            logger.debug("schema cleanup: removed %d old file(s)", removed)
        schema_note = (
            f"Google Jobs schema (JSON-LD) saved to {schema_path} — paste it "
            "into the page <head> when publishing."
        )
    except OSError as e:
        logger.debug("could not write schema file: %s", e)

    footer_lines = []
    if seo_score is not None:
        if seo_score >= SEO_MIN_SCORE:
            footer_lines.append(f"SEO Score (Gemini audit): {seo_score}/100 ✓")
        else:
            footer_lines.append(
                f"SEO Score (Gemini audit): {seo_score}/100 — best of "
                f"{SEO_MAX_IMPROVE_ROUNDS} improvement rounds, target {SEO_MIN_SCORE}. "
                "Remaining: " + "; ".join(seo_issues[:3])
            )
        if seo_precheck_issues:
            footer_lines.append(
                "Checklist warnings: " + "; ".join(seo_precheck_issues[:3])
            )
    if schema_note:
        footer_lines.append(schema_note)

    footer = ""
    if footer_lines:
        footer = "\n\n" + ("-" * 40) + "\n" + "\n".join(footer_lines)
    if schema_note is None:
        # Fallback: file write failed, keep the schema visible so it isn't lost.
        footer += (
            "\n\nTECHNICAL SEO: JOB POSTING SCHEMA\n"
            "(Could not save to a file — paste this in the page <head> when "
            "publishing.)\n\n" + schema_blocks
        )

    return blog + footer


def _strip_markdown(text: str) -> str:
    """Return the blog as clean plain text for console display: drop '#' heading
    markers and '**' bold markers, and turn '*'/'-' list bullets into '•'.
    Apply links are left as [text](url) so the URL stays with its label."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)   # "## Title" -> "Title"
        line = re.sub(r"^(\s*)[*-]\s+", r"\1• ", line)  # "* item" / "- item" -> "• item"
        line = line.replace("**", "").replace("*", "")  # drop bold / stray emphasis
        lines.append(line)
    return "\n".join(lines)


# ─── Retired: formatters for the old openwebninja/JSearch tools ─────────────
# def _money(value, currency: str) -> str:
#     """Format a salary number with thousands separators, e.g. 'USD 143,100'."""
#     if value is None:
#         return "?"
#     return f"{currency} {round(value):,}".strip()
#
#
# def _format_salary(est: dict) -> str:
#     """Render one salary-estimate record into a readable block.
#     Shared by get_estimated_salary and get_company_salary; the company line
#     only appears when the record includes a company."""
#     title = est.get("job_title", "this role")
#     loc = est.get("location", "the area")
#     company = est.get("company", "")
#     currency = est.get("salary_currency", "")
#     period = (est.get("salary_period") or "").lower()
#     per = f" / {period}" if period else ""
#
#     median = _money(est.get("median_salary"), currency)
#     low = _money(est.get("min_salary"), currency)
#     high = _money(est.get("max_salary"), currency)
#
#     confidence = est.get("confidence", "")
#     publisher = est.get("publisher_name", "")
#     count = est.get("salary_count")
#
#     header = f"Estimated salary for {title}"
#     if company:
#         header += f" at {company}"
#     header += f" in {loc}:"
#
#     lines = [
#         header,
#         f"   Median: {median}{per}",
#         f"   Range:  {low} - {high}{per}",
#     ]
#
#     # Base vs additional pay, when present.
#     base_median = est.get("median_base_salary")
#     add_median = est.get("median_additional_pay")
#     if base_median is not None:
#         lines.append(f"   Base (median): {_money(base_median, currency)}{per}")
#     if add_median is not None:
#         lines.append(f"   Additional pay (median): {_money(add_median, currency)}{per}")
#
#     source_bits = []
#     if publisher:
#         source_bits.append(publisher)
#     if count is not None:
#         source_bits.append(f"{count} salaries")
#     if confidence:
#         source_bits.append(f"confidence: {confidence}")
#     if source_bits:
#         lines.append(f"   Source: {', '.join(source_bits)}")
#
#     return "\n".join(lines)
#
#
# def _format_job_detail(job: dict) -> str:
#     """Render one job-details record into a readable block."""
#     title = job.get("job_title", "Unknown role")
#     company = job.get("employer_name", "Unknown company")
#     website = job.get("employer_website", "")
#     loc = job.get("job_location") or "N/A"
#
#     # Remote: job_is_remote is sometimes null; work_arrangement is more reliable.
#     if job.get("job_is_remote") is True:
#         remote = "Yes"
#     elif job.get("work_arrangement"):
#         remote = job["work_arrangement"]            # e.g. remote / hybrid / onsite
#     else:
#         remote = "No"
#
#     employment = job.get("job_employment_type", "")
#     posted = job.get("job_posted_at") or job.get("job_posted_at_datetime_utc") or "N/A"
#     publisher = job.get("job_publisher", "")
#
#     # Seniority / experience.
#     seniority = job.get("seniority_level", "")
#     exp = job.get("required_experience_years")
#     exp_str = f"{exp}+ years" if exp else ""
#
#     # Salary: this API gives min/max/period, not a ready-made string.
#     lo, hi = job.get("job_min_salary"), job.get("job_max_salary")
#     period = job.get("job_salary_period", "")
#     if lo or hi:
#         salary = f"{lo or '?'} - {hi or '?'}" + (f" / {period.lower()}" if period else "")
#     else:
#         salary = "Not specified"
#
#     skills = job.get("required_technologies") or []
#     apply_options = job.get("apply_options") or []
#     reviews = job.get("employer_reviews") or []
#
#     description = (job.get("job_description") or "").strip()
#     if len(description) > 1500:
#         description = description[:1500].rstrip() + " ..."
#
#     highlights = job.get("job_highlights") or {}
#
#     def fmt_section(name: str) -> str:
#         items = highlights.get(name) or []
#         if not items:
#             return ""
#         bullets = "\n".join(f"   - {x}" for x in items)
#         return f"\n\n{name}:\n{bullets}"
#
#     parts = [
#         f"{title} — {company}",
#         f"Location: {loc} | Remote: {remote}",
#         f"Employment: {employment or 'N/A'} | Posted: {posted}",
#         f"Salary: {salary}",
#     ]
#     level_bits = " | ".join(b for b in (seniority, exp_str) if b)
#     if level_bits:
#         parts.append(f"Level: {level_bits}")
#     if skills:
#         parts.append(f"Key skills: {', '.join(skills)}")
#     if website:
#         parts.append(f"Company site: {website}")
#     if publisher:
#         parts.append(f"Listed via: {publisher}")
#
#     out = "\n".join(parts)
#
#     out += fmt_section("Qualifications")
#     out += fmt_section("Responsibilities")
#     out += fmt_section("Benefits")
#
#     if reviews:
#         review_lines = []
#         for r in reviews:
#             score = r.get("score")
#             if score is None:
#                 continue
#             pub = r.get("publisher", "")
#             cnt = r.get("review_count", "?")
#             maxs = r.get("max_score", 5)
#             review_lines.append(f"   - {pub}: {score}/{maxs} ({cnt} reviews)")
#         if review_lines:
#             out += "\n\nEmployer reviews:\n" + "\n".join(review_lines)
#
#     if apply_options:
#         opt_lines = [
#             f"   - {o.get('publisher', 'Link')}: {o.get('apply_link', '')}"
#             for o in apply_options[:5]
#         ]
#         out += "\n\nApply options:\n" + "\n".join(opt_lines)
#     else:
#         out += f"\n\nApply: {job.get('job_apply_link', 'N/A')}"
#
#     if description:
#         out += f"\n\nDescription:\n{description}"
#
#     return out


tools = [
    get_weather,
    search_web,
    search_jobs,
    write_job_blog,
]
TOOLS_BY_NAME = {t.name: t for t in tools}

# These tools already return a clean, formatted, ready-to-read result. Their
# output is shown to the user directly (see print_stream) and the turn ends
# after they run (see after_tools) — so the model never re-summarizes a job
# list nor chains an unrequested follow-up call onto a search.
DISPLAY_TOOL_OUTPUT = {
    "search_jobs",
    "write_job_blog",
}

# Tool-routing model: poolside/laguna-m.1:free, served via OpenRouter's
# OpenAI-compatible endpoint. We point LangChain's ChatOpenAI at OpenRouter's
# base URL so .bind_tools() and the existing LangGraph flow keep working
# unchanged. `extra_body` carries OpenRouter-specific params straight through to
# the request body — here we turn on reasoning so the model thinks step-by-step
# before routing to a tool. A modest non-zero temperature keeps tool-call
# syntax from getting stuck in a single bad pattern.
llm_model = ChatOpenAI(
    model="poolside/laguna-m.1:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.5,
    extra_body={"reasoning": {"enabled": True}},
    # Optional: surface your app on the OpenRouter leaderboards.
    # default_headers={"HTTP-Referer": "https://your-site", "X-Title": "Agent_J"},
).bind_tools(tools)

# ─── Retired: Groq summarizer for the tool_use_failed salvage path ──────────
# The routing model (llm_model) is now OpenRouter/ChatOpenAI, not ChatGroq, so
# BadRequestError/RateLimitError (groq SDK exceptions) can no longer be raised
# by app.stream() below — this salvage path is currently dead code. Left
# commented out, along with salvage_failed_tool_call/summarize_tool_result and
# the matching except blocks in run_with_retry, in case a Groq-routed model is
# reintroduced later.
# summarizer = ChatGroq(
#     model="llama-3.1-8b-instant",
#     temperature=0.3,
#     groq_api_key=os.getenv("GROQ_API_KEY"),
# )

def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"


def after_tools(state: AgentState) -> str:
    """Decide where to go after the tools node.
    Display tools (job list, blog post) already print their full result to the
    user, so end the turn. Other tools (weather, web search) loop back so the
    model can compose a reply from their output."""
    for message in reversed(state["messages"]):
        if isinstance(message, ToolMessage):
            return "end" if message.name in DISPLAY_TOOL_OUTPUT else "continue"
        if isinstance(message, AIMessage):
            break
    return "continue"


# ─── Provider-error handling for the OpenRouter model ───────────────────────
# OpenRouter sometimes returns a transient upstream error (e.g. a 502 "Provider
# returned error" on a free model). langchain_openai surfaces that as a plain
# ValueError({'message': ..., 'code': ...}); the openai SDK raises APIError
# subclasses carrying a status_code. We retry the transient ones at the node
# level (see RetryPolicy below) and report the rest cleanly instead of crashing.

def _provider_error_text(exc) -> str | None:
    """If exc looks like an OpenRouter/OpenAI provider error, return a short
    human-readable description; otherwise None (so real bugs aren't swallowed)."""
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], dict):
        info = exc.args[0]
        code = info.get("code")
        msg = info.get("message", "provider error")
        return msg + (f" (code {code})" if code is not None else "")
    if isinstance(exc, openai.APIError):
        code = getattr(exc, "status_code", None)
        return exc.__class__.__name__ + (f" (HTTP {code})" if code else "")
    return None


def _is_transient_provider_error(exc) -> bool:
    """For the node RetryPolicy: retry only transient failures — provider/HTTP
    5xx and 429, plus connection/timeout blips — which usually clear on retry."""
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], dict):
        code = exc.args[0].get("code")
        return code == 429 or (isinstance(code, int) and 500 <= code <= 599)
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError,
                        openai.InternalServerError, openai.RateLimitError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        code = getattr(exc, "status_code", None)
        return code == 429 or (isinstance(code, int) and 500 <= code <= 599)
    return False


# ─── Malformed tool-call safety net (OpenRouter version) ────────────────────
# This replaces the old Groq tool_use_failed retry/salvage path (see the
# commented-out code near summarizer / salvage_failed_tool_call / run_with_retry
# below). It is NOT a like-for-like port: Groq's BadRequestError carried a
# `failed_generation` string with the literal mangled `<function=...>` text, so
# the old code could regex it out and manually invoke the tool. OpenRouter (per
# https://openrouter.ai/docs/api/reference/errors-and-debugging) normalizes
# provider errors into `error.message` / `error.code` / `error.metadata`, with
# no documented, provider-agnostic field guaranteed to hold a parseable raw
# tool call — so an equivalent "salvage and invoke it ourselves" step isn't
# reliably buildable across the different upstream providers OpenRouter proxies.
# Instead, this only RETRIES the turn (giving the model, run at temperature=0.5,
# a fresh chance to produce a well-formed tool call) and, if that keeps failing,
# falls through to the plain apology message already at the end of
# run_with_retry.
def _is_malformed_tool_call_error(exc) -> bool:
    """True if a 400 from the OpenRouter/openai SDK looks like the model
    produced a broken/unparseable tool call — worth retrying, since resampling
    often fixes it — rather than a genuine bug in our own request (bad schema,
    wrong message ordering, invalid params), where retrying would just fail
    identically. This is a keyword heuristic, not an exact match on a stable
    OpenRouter error code, because no such code is documented for this
    specific failure mode; extend the `signals` tuple if you observe other
    wording for the same underlying problem."""
    if not isinstance(exc, openai.BadRequestError):
        return False
    body = getattr(exc, "body", None) or {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    message = str(error.get("message") or exc).lower()
    signals = (
        "tool_use_failed",
        "failed to parse",
        "could not parse",
        "malformed",
        "invalid tool call",
        "invalid function call",
    )
    return any(s in message for s in signals)


graph = StateGraph(AgentState)

# Retry transient provider errors (502/429/connection) inside the node, with
# backoff. Doing it here — rather than re-running app.stream from the outside —
# means the retry does NOT re-append the user's message to the saved thread.
graph.add_node(
    "Agent_J",
    model_call,
    retry_policy=RetryPolicy(
        max_attempts=4,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=_is_transient_provider_error,
    ),
)

tool_node = ToolNode(tools=tools)
graph.add_node("tools", tool_node)

graph.add_edge(START, "Agent_J")

graph.add_conditional_edges(
    "Agent_J",
    should_continue,
    {
        "continue": "tools",
        "end": END
    }
)

graph.add_conditional_edges(
    "tools",
    after_tools,
    {
        "continue": "Agent_J",
        "end": END,
    },
)

# Compile with an in-memory checkpointer so the conversation persists across
# turns: each new question is APPENDED to the same thread (see add_messages),
# letting the model see what it already told the user — e.g. a job_id it showed
# earlier — instead of starting blank every time. Memory lasts for the life of
# the process; restart the program (or use a new thread_id) to clear it.
checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)

# A checkpointer needs a thread_id to know which conversation to load/append to.
# One id = one running session here; swap it to isolate separate chats.
SESSION_CONFIG = {"configurable": {"thread_id": "agent_j_session"}}

def print_stream(stream):
    for s in stream:
        message = s["messages"][-1]
        if isinstance(message, ToolMessage) and message.name in DISPLAY_TOOL_OUTPUT:
            # The full job list / details / blog, shown verbatim to the user.
            # Label it with the agent's name so it's clear Agent_J is replying.
            print("\nAgent_J:\n\n" + str(message.content).lstrip("\n"), flush=True)
        elif isinstance(message, AIMessage) and not message.tool_calls and message.content:
            print("\nAgent_J:\n\n" + str(message.content).lstrip("\n"), flush=True)


# ─── Retired: Groq tool_use_failed salvage helpers ──────────────────────────
# These pulled a mangled tool call out of a Groq BadRequestError payload and
# ran it manually. Groq exceptions can't be raised by app.stream() anymore
# (see the summarizer note above), so this path is unreachable. Left
# commented out in case a Groq-routed model is reintroduced later.
# def salvage_failed_tool_call(error: BadRequestError) -> str | None:
#     """Last-resort fallback: pull the mangled tool call out of Groq's error
#     payload and run it manually. Returns the raw tool output (which is then
#     handed to the summarizer so the user sees prose, not JSON)."""
#     body = getattr(error, "body", None) or {}
#     failed = body.get("error", {}).get("failed_generation", "")
#     # Matches both <function=name{...} and <function=name,{...} variants.
#     m = re.search(r"<function=(\w+).*?(\{.*\})", failed, re.DOTALL)
#     if not m:
#         return None
#     name, raw_args = m.group(1), m.group(2)
#     tool_fn = TOOLS_BY_NAME.get(name)
#     if tool_fn is None:
#         return None
#     try:
#         args = json.loads(raw_args)
#         return tool_fn.invoke(args)
#     except Exception:
#         return None
#
#
# def summarize_tool_result(query: str, raw_result: str) -> str:
#     """Turn a raw tool result into a clean answer for the user."""
#     prompt = [
#         SystemMessage(content=(
#             "You are Agent_J. The user asked a question and a tool returned "
#             "raw results. Write a clear, concise answer based only on those "
#             "results. Do not mention JSON, search, or tools. Cite the source links "
#             "where useful."
#         )),
#         ("user", f"User's question: {query}\n\nTool results:\n{raw_result}"),
#     ]
#     return summarizer.invoke(prompt).content


def run_with_retry(inputs, max_attempts=4):
    # The loop retries when the model produces a malformed tool call (see
    # _is_malformed_tool_call_error) — resampling at temperature=0.5 often
    # produces a well-formed call on the next attempt. All other error types
    # return immediately (see each branch below); if every attempt is a
    # malformed tool call, the loop falls through to the apology message.
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            print_stream(app.stream(inputs, SESSION_CONFIG, stream_mode="values"))
            return
        except ValueError as e:
            # OpenRouter provider error surfaced by langchain_openai. Transient
            # ones (5xx/429) were already retried at the node; if we still land
            # here the provider is failing. Report cleanly — do NOT re-invoke,
            # which would duplicate the user's message in the saved thread. Any
            # ValueError that is NOT a provider error is a real bug: re-raise.
            text = _provider_error_text(e)
            if text is None:
                raise
            print(
                "\nAgent_J: The model provider returned an error (" + text +
                "). This is usually temporary — please try again in a moment.",
                flush=True,
            )
            return
        except openai.BadRequestError as e:
            # Must be caught before the generic openai.APIError below, since
            # BadRequestError is a subclass of it. Only retry when the 400
            # looks like a malformed tool call from the model (see
            # _is_malformed_tool_call_error's docstring for why this is a
            # heuristic rather than an exact provider error code match); any
            # other 400 (bad schema, invalid params, etc.) is a real bug in
            # our own request and retrying it would just fail identically, so
            # it's re-raised instead of silently retried or swallowed.
            if not _is_malformed_tool_call_error(e):
                raise
            last_error = e
            if attempt < max_attempts:
                logger.debug(
                    "possible malformed tool call from the model, retrying %d/%d",
                    attempt,
                    max_attempts - 1,
                )
        except openai.APIError as e:
            # Auth/connection/other OpenRouter API errors. Report, don't crash.
            text = _provider_error_text(e) or str(e)
            print(
                "\nAgent_J: I couldn't reach the model just now (" + text +
                "). Please check your OPENROUTER_API_KEY / connection and try again.",
                flush=True,
            )
            return
        # ── Retired: Groq-specific exceptions (see note above) ──────────────
        # except RateLimitError as e:
        #     # Token/request quota hit — retrying immediately won't help, so tell
        #     # the user plainly (including the API's "try again in ..." hint).
        #     message = str(e)
        #     try:
        #         message = e.body.get("error", {}).get("message", message)
        #     except Exception:
        #         pass
        #     print(
        #         "\nAgent_J: I've hit the Groq rate limit, so I can't answer right "
        #         "now. " + message,
        #         flush=True,
        #     )
        #     return
        # except BadRequestError as e:
        #     if "tool_use_failed" not in str(e):
        #         raise  # a real error — don't swallow it
        #     last_error = e
        #     if attempt < max_attempts:
        #         logger.debug(
        #             "tool-call glitch, retrying %d/%d",
        #             attempt,
        #             max_attempts - 1,
        #         )

    # All retries exhausted. Previously (Groq) this salvaged the mangled tool
    # call and summarized it into a proper answer. There's no reliable,
    # provider-agnostic raw payload to salvage from OpenRouter (see the note
    # above _is_malformed_tool_call_error), so this is a plain fallback
    # message instead.
    print("\nAgent_J: The model kept mangling its tool call. Try rephrasing.", flush=True)


if __name__ == "__main__":
    print("Hi, I'm Agent_J. Ask me a question (or type 'quit' to exit).")

    while True:
        user_question = input("\nYou: ").strip()

        if user_question.lower() in ("quit", "exit", "q", "bye"):
            print("\nGoodBye! See you soon.")
            break

        if not user_question:
            continue

        inputs = {"messages": [("user", user_question)]}
        run_with_retry(inputs)