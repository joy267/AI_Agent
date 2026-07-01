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
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RetryPolicy
import requests
import openai
from groq import BadRequestError, RateLimitError
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
        f"vacancies, or work-from-home roles. Each result includes a Job ID. "
        f"After search_jobs, just present the results; do NOT call "
        f"get_job_details automatically. Only call get_job_details when the "
        f"user explicitly asks about a specific job or gives you a Job ID, "
        f"and pass the same country code you used in search_jobs. "
        f"When the user asks how much a role pays or about expected salary for "
        f"a job title in a location, use the get_estimated_salary tool. "
        f"When the user asks about pay for a role at a specific named company, "
        f"use the get_company_salary tool. For a whole-country location like "
        f"'India', set location_type=COUNTRY on these salary tools so it is not "
        f"matched to a similarly named city such as Indianapolis. "
        f"When the user asks you to write, create, or draft a blog post or "
        f"article about available jobs, use the write_job_blog tool — pass a "
        f"query to feature several jobs, or a job_id to feature one specific job. "
        f"If the user asks about, or asks you to write a blog for, a specific "
        f"job you already showed earlier in this conversation, reuse that job's "
        f"Job ID from the earlier results (pass it as job_id) instead of "
        f"searching again by title — searching by title may return a different "
        f"posting."
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


def _extract_jobs_and_cursor(payload: dict):
    """search-v2 nests results differently from the other endpoints: the docs
    refer to `data.cursor`, meaning `data` is an OBJECT holding both the jobs
    array and the next-page cursor — whereas job-details/salary return `data`
    as a flat list. This handles either shape and finds the jobs list even if
    its key name varies, returning (jobs_list, cursor)."""
    raw = payload.get("data")
    cursor = payload.get("cursor")

    # Shape A: data is already the list of jobs.
    if isinstance(raw, list):
        return raw, cursor

    # Shape B: data is an object containing the jobs list + cursor.
    if isinstance(raw, dict):
        cursor = raw.get("cursor", cursor)
        for key in ("jobs", "data", "results", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return val, cursor
        # Fallback: first value that looks like a list of job objects.
        for val in raw.values():
            if isinstance(val, list) and (not val or isinstance(val[0], dict)):
                return val, cursor
        return [], cursor

    return [], cursor


def _fetch_jobs(query, country, date_posted, work_from_home, max_results, max_pages):
    """Fetch job dicts from search-v2, walking cursor pagination until the API
    runs out of results, max_results is reached, or max_pages is hit. Returns
    (jobs_list, error) where error is an exception/str or None. Shared by
    search_jobs and write_job_blog."""
    api_key = os.getenv("JSEARCH_API_KEY")
    if not api_key:
        return [], "JSEARCH_API_KEY is not set"

    url = "https://api.openwebninja.com/jsearch/search-v2"
    headers = {"x-api-key": api_key}

    all_jobs = []
    cursor = None
    error = None

    # Walk cursor pagination one page at a time until the API runs out of
    # results, we have enough (max_results), or we hit the page cap (credits).
    for _ in range(max(1, max_pages)):
        params = {
            "query": query,
            "country": country,
            "date_posted": date_posted,
            "work_from_home": str(work_from_home).lower(),
            "num_pages": 1,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            error = e
            break  # stop paging but keep whatever we already collected

        page_jobs, cursor = _extract_jobs_and_cursor(payload)
        # Guard against any stray non-dict entries so formatters can't crash.
        page_jobs = [j for j in page_jobs if isinstance(j, dict)]
        all_jobs.extend(page_jobs)

        if len(all_jobs) >= max_results:
            all_jobs = all_jobs[:max_results]
            break
        if not cursor or not page_jobs:
            break

    return all_jobs, error


@tool
def search_jobs(
    query: str,
    country: str = "in",
    date_posted: str = "today",
    work_from_home: bool = False,
    max_results: int = 50,
    max_pages: int = 10,
) -> str:
    """Search for real-time job listings (Google for Jobs aggregate).
    Walks the API's cursor pagination to gather results, stopping when the API
    runs out of results, max_results is reached, or max_pages is reached.
    Use this when the user wants to find jobs, openings, vacancies, or
    work-from-home roles. Each result includes a Job ID that can be passed to
    get_job_details for the full posting.

    query: include job title AND location, e.g. "python developer in kolkata".
    country: two-letter ISO code matching the location, e.g. "us", "in", "de".
    date_posted: one of "all", "today", "3days", "week", "month".
    work_from_home: True to return only remote / WFH jobs.
    max_results: hard cap on total jobs returned (default 50).
    max_pages: safety cap on pages pulled. Each page is up to 10 jobs and costs
               1 API credit. Default 10."""

    all_jobs, error = _fetch_jobs(
        query, country, date_posted, work_from_home, max_results, max_pages
    )
    if not all_jobs:
        if error:
            return f"Job search failed: {error}"
        return f"No jobs found for '{query}'."

    lines = []
    for i, job in enumerate(all_jobs, start=1):
        title = job.get("job_title", "Unknown role")
        company = job.get("employer_name", "Unknown company")

        # search-v2 usually gives a combined job_location; fall back to parts.
        loc = job.get("job_location") or ", ".join(
            p for p in (job.get("job_city"), job.get("job_state"), job.get("job_country"))
            if p
        ) or "N/A"

        # job_is_remote can be null even for remote roles; work_arrangement is
        # the more reliable signal in this API.
        is_remote = job.get("job_is_remote") is True or job.get("work_arrangement") == "remote"
        remote = " (Remote)" if is_remote else ""
        employment = job.get("job_employment_type", "")
        posted = job.get("job_posted_at") or job.get("job_posted_at_datetime_utc") or "N/A"
        link = job.get("job_apply_link", "N/A")
        job_id = job.get("job_id", "N/A")

        # Compact: a scannable summary line, with the long ID + apply link on an
        # indented continuation so the main list stays easy to read.
        summary = [f"{title} — {company}", f"{loc}{remote}", posted]
        if employment:
            summary.append(employment)
        line = f"{i}. " + " | ".join(summary) + f"\n   ID: {job_id} | Apply: {link}"
        lines.append(line)

    # If we stopped early because of an error, the list is partial — still useful.
    note = f" (partial: {error})" if error else ""
    header = f"Found {len(all_jobs)} jobs for '{query}'{note}:\n\n"
    return header + "\n".join(lines)


def _fetch_job_details(job_id, country):
    """Fetch raw job-details dicts for one or more (comma-separated) Job IDs.
    Returns (jobs_list, error). The endpoint 500s on a country mismatch and can
    fail transiently, so we try with the country then fall back to omitting it.
    Shared by get_job_details and write_job_blog."""
    api_key = os.getenv("JSEARCH_API_KEY")
    if not api_key:
        return [], "JSEARCH_API_KEY is not set"

    url = "https://api.openwebninja.com/jsearch/job-details"
    headers = {"x-api-key": api_key}
    attempts = [{"job_id": job_id, "country": country}, {"job_id": job_id}]
    last_error = None
    for params in attempts:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            jobs = [j for j in (data.get("data") or []) if isinstance(j, dict)]
            return jobs, None
        except Exception as e:
            last_error = e
    return [], last_error


@tool
def get_job_details(job_id: str, country: str = "in") -> str:
    """Get the full details of a specific job using its Job ID.
    Call this after search_jobs when the user wants to know more about a
    particular job: full description, qualifications, responsibilities,
    benefits, salary range, employer reviews, and how to apply.

    job_id: the Job ID returned by search_jobs. Up to 20 comma-separated IDs
            are supported (each counts as one request).
    country: two-letter ISO code. Use the SAME country you searched with, as a
             mismatch can make this endpoint fail."""

    jobs, error = _fetch_job_details(job_id, country)
    if not jobs:
        if error:
            return f"Failed to fetch job details: {error}"
        return f"No details found for job_id '{job_id}'."

    return "\n\n" + ("\n\n" + ("=" * 40) + "\n\n").join(
        _format_job_detail(job) for job in jobs
    )


@tool
def get_estimated_salary(
    job_title: str,
    location: str,
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> str:
    """Get the estimated salary / pay for a job title at a location.
    Use this when the user asks how much a role pays, the salary range, or the
    expected compensation for a kind of job somewhere (no specific company).
    The currency in the result follows the location (e.g. INR for India).

    job_title: e.g. "nodejs developer", "data analyst".
    location: e.g. "new york", "kolkata, india", "India".
    location_type: one of ANY, CITY, STATE, COUNTRY. For a whole country such as
                   "India", set this to COUNTRY so it is not mismatched to a
                   similarly named city (e.g. Indianapolis).
    years_of_experience: one of ALL, LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX,
                         SEVEN_TO_NINE, TEN_TO_FOURTEEN, ABOVE_FIFTEEN."""

    api_key = os.getenv("JSEARCH_API_KEY")
    if not api_key:
        return "Salary estimation is unavailable: JSEARCH_API_KEY is not set."

    url = "https://api.openwebninja.com/jsearch/estimated-salary"
    headers = {"x-api-key": api_key}
    params = {
        "job_title": job_title,
        "location": location,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return f"Salary estimation failed: {e}"

    estimates = data.get("data", []) or []
    if not estimates:
        return f"No salary data found for '{job_title}' in '{location}'."

    return "\n\n".join(_format_salary(est) for est in estimates)


@tool
def get_company_salary(
    company: str,
    job_title: str,
    location: str = "",
    location_type: str = "ANY",
    years_of_experience: str = "ALL",
) -> str:
    """Get the estimated pay for a job title at a SPECIFIC named company.
    Use this when the user asks how much a role pays at a particular employer,
    e.g. "how much does a software developer make at Amazon?".
    The currency in the result follows the location (e.g. INR for India).

    company: the employer name, e.g. "Amazon", "Google".
    job_title: e.g. "software developer", "data scientist".
    location: optional free-text area, e.g. "seattle", "India". Leave empty for
              a company-wide estimate.
    location_type: one of ANY, CITY, STATE, COUNTRY. For a whole country such as
                   "India", set this to COUNTRY so it is not mismatched to a
                   similarly named city (e.g. Indianapolis).
    years_of_experience: one of ALL, LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX,
                         SEVEN_TO_NINE, TEN_TO_FOURTEEN, ABOVE_FIFTEEN."""

    api_key = os.getenv("JSEARCH_API_KEY")
    if not api_key:
        return "Salary estimation is unavailable: JSEARCH_API_KEY is not set."

    url = "https://api.openwebninja.com/jsearch/company-job-salary"
    headers = {"x-api-key": api_key}
    params = {
        "company": company,
        "job_title": job_title,
        "location_type": location_type,
        "years_of_experience": years_of_experience,
    }
    if location:
        params["location"] = location

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return f"Salary estimation failed: {e}"

    estimates = data.get("data", []) or []
    if not estimates:
        return f"No salary data found for '{job_title}' at '{company}'."

    return "\n\n".join(_format_salary(est) for est in estimates)


# ─── Gemini (Google AI Studio) — used only to WRITE blog prose ──────────────
# The blog text is written by Gemini, while the job FACTS still come from the
# JSearch API (so the post can't invent salaries, links, or requirements). Model
# / timeout / retry policy are env-configurable. The Groq `summarizer` defined
# later is unrelated and stays for the tool-call salvage path.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "60000"))
GEMINI_MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))


def _gemini_generate(system_text: str, user_text: str):
    """Call Gemini once to turn a grounded prompt into prose.
    Returns (text, error): on success error is None; on failure text is None and
    error is a short human-readable string. Retries transient 5xx / 429 errors
    with exponential backoff; a bad key (401/403) and other 4xx fail fast."""
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
                    temperature=0.7,
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

@tool
def write_job_blog(
    query: str = "",
    job_id: str = "",
    country: str = "in",
    date_posted: str = "week",
    work_from_home: bool = False,
    max_results: int = 10,
) -> str:
    """Write a professional, SEO-optimized, ready-to-publish blog post for an Indian job portal.
    Uses Google Gemini to transform job data into a high-ranking career article.
    """

    if job_id:
        jobs, error = _fetch_job_details(job_id, country)
        topic = f"the {jobs[0].get('job_title', 'role')} role" if jobs else job_id
    else:
        if not query:
            return "Please provide either a query or a job_id to write a blog about."
        pages = max(1, (max_results + 9) // 10)
        jobs, error = _fetch_jobs(
            query, country, date_posted, work_from_home, max_results, pages
        )
        topic = query

    if not jobs:
        if error:
            return f"Could not fetch job data to write the blog: {error}"
        return f"No jobs found for '{topic}', so there is nothing to write about."

    # Prepare grounded data for the AI
    blocks = []
    for job in jobs:
        # --- LINK SAFETY LOGIC ---
        # Prioritize official company website over third-party aggregators
        official_link = job.get("job_apply_link", "")
        employer_site = job.get("employer_website", "")
        apply_options = job.get("apply_options", [])
        
        # If apply_options exist, look for a link that matches the company domain
        if apply_options and employer_site:
            domain = employer_site.replace("https://", "").replace("http://", "").replace("www.", "").split('/')[0]
            for option in apply_options:
                link = option.get("apply_link", "")
                if domain in link:
                    official_link = link
                    break

        title = job.get("job_title", "N/A")
        company = job.get("employer_name", "N/A")
        loc = job.get("job_location") or f"{job.get('job_city', '')}, {job.get('job_state', '')}".strip(", ") or "India"
        
        lo, hi = job.get("job_min_salary"), job.get("job_max_salary")
        currency = job.get("job_salary_currency", "INR")
        salary = f"{currency} {lo} - {hi}" if lo and hi else "Best in Industry"
        
        exp = job.get("required_experience_years")
        exp_str = f"{exp}+ years" if exp else "Not specified (Check description)"
        
        desc = (job.get("job_description") or "").strip()
        highlights = job.get("job_highlights") or {}
        quals = highlights.get("Qualifications") or []
        resps = highlights.get("Responsibilities") or []

        fields = [
            f"Title: {title}",
            f"Company: {company}",
            f"Location: {loc}",
            f"Salary: {salary}",
            f"Experience: {exp_str}",
            f"Qualifications: {'; '.join(quals[:5])}",
            f"Responsibilities: {'; '.join(resps[:5])}",
            f"Description: {desc[:800]}...",
            f"OfficialApplyLink: {official_link}"
        ]
        blocks.append("\n".join(fields))

    job_data = ("\n\n" + ("-" * 20) + "\n\n").join(blocks)

    system_text = (
        "Act as a Senior SEO Strategist and Job Portal Content Editor. "
        "Your goal is to write a high-ranking blog post for an Indian job seeker audience.\n\n"
        
        "STRICT FORMATTING RULES:\n"
        "1. DO NOT use '#' for headings. Use UPPERCASE plain text for main titles and Normal Case for subheadings.\n"
        "2. DO NOT use '**' or '*' for bold/italics. Use plain text.\n"
        "3. Use '•' for all bullet points.\n"
        "4. Start with 'SEO title:' (max 60 chars), 'Meta description:' (150-160 chars), and 'Suggested URL Slug:'.\n\n"
        
        "CONTENT STRUCTURE (MANDATORY SECTIONS):\n"
        "- MAIN TITLE: <Role Name> Recruitment 2024 at <Company Name>\n"
        "- Intro: Hook the reader about the career opportunity.\n"
        "- Job Overview Table: Include Columns: Company Name, Job Role, Salary, Location, Eligibility, Experience Required.\n"
        "- Job Role & Responsibilities: Use bullet points.\n"
        "- Eligibility Criteria: Education and skills.\n"
        "- Selection Process: Describe a 3-4 step process (Assessment, Technical, HR).\n"
        "- Documents to Carry: List essential items (Resume, Aadhar, Education certs, etc.).\n"
        "- How to Apply: Step-by-step guide.\n"
        "- Official Apply Link: Use the provided OfficialApplyLink. Mention: 'Note: Always apply through official company portals to avoid fraud.'\n"
        "- Employer Reviews Section Logic: If a rating is available, do not just list the number. Break it down into sub-categories: Work-Life Balance, Career Growth, and Compensation. Provide a 1-sentence summary of the company 'Vibe' based on the job description (e.g., 'Tech-driven,' 'Collaborative,' or 'Fast-paced'). This builds trust with the candidate."
        "- Frequently Asked Questions: 3-4 clear Q&A pairs.\n"
        "- Related Jobs: Suggest 5-8 similar job roles which you get from the search_jobs tool call. Show the job titles and it's application link.\n"
        
        "TONE & SEO:\n"
        "- Use keywords: 'Recruitment 2024', 'Latest Jobs in India', 'Job Vacancy'.\n"
        "- If details are missing, use 'As per Company Norms'.\n"
    )
    
    user_text = f"Topic: {topic}\n\nJob Data:\n{job_data}"

    blog, gen_error = _gemini_generate(system_text, user_text)
    if blog is None:
        return f"Failed to write the SEO blog: {gen_error}"

    return _strip_markdown(blog)


def _strip_markdown(text: str) -> str:
    """
    Cleans the output for a professional display:
    1. Removes all '#' heading markers.
    2. Removes all '**' and '*' bold/italic markers.
    3. Maintains Markdown links [text](url) but removes bolding around them.
    4. Ensures list bullets are standardized to '•'.
    """
    lines = []
    for line in text.splitlines():
        # Remove markdown heading markers
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        
        # Convert bullets to standard '•'
        line = re.sub(r"^(\s*)[*-]\s+", r"\1• ", line)
        
        # Remove bold and italic formatting
        line = line.replace("**", "").replace("__", "").replace("*", "_").replace("_", "")
        
        lines.append(line)
        
    return "\n".join(lines).strip()


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


def _money(value, currency: str) -> str:
    """Format a salary number with thousands separators, e.g. 'USD 143,100'."""
    if value is None:
        return "?"
    return f"{currency} {round(value):,}".strip()


def _format_salary(est: dict) -> str:
    """Render one salary-estimate record into a readable block.
    Shared by get_estimated_salary and get_company_salary; the company line
    only appears when the record includes a company."""
    title = est.get("job_title", "this role")
    loc = est.get("location", "the area")
    company = est.get("company", "")
    currency = est.get("salary_currency", "")
    period = (est.get("salary_period") or "").lower()
    per = f" / {period}" if period else ""

    median = _money(est.get("median_salary"), currency)
    low = _money(est.get("min_salary"), currency)
    high = _money(est.get("max_salary"), currency)

    confidence = est.get("confidence", "")
    publisher = est.get("publisher_name", "")
    count = est.get("salary_count")

    header = f"Estimated salary for {title}"
    if company:
        header += f" at {company}"
    header += f" in {loc}:"

    lines = [
        header,
        f"   Median: {median}{per}",
        f"   Range:  {low} - {high}{per}",
    ]

    # Base vs additional pay, when present.
    base_median = est.get("median_base_salary")
    add_median = est.get("median_additional_pay")
    if base_median is not None:
        lines.append(f"   Base (median): {_money(base_median, currency)}{per}")
    if add_median is not None:
        lines.append(f"   Additional pay (median): {_money(add_median, currency)}{per}")

    source_bits = []
    if publisher:
        source_bits.append(publisher)
    if count is not None:
        source_bits.append(f"{count} salaries")
    if confidence:
        source_bits.append(f"confidence: {confidence}")
    if source_bits:
        lines.append(f"   Source: {', '.join(source_bits)}")

    return "\n".join(lines)


def _format_job_detail(job: dict) -> str:
    """Render one job-details record into a readable block."""
    title = job.get("job_title", "Unknown role")
    company = job.get("employer_name", "Unknown company")
    website = job.get("employer_website", "")
    loc = job.get("job_location") or "N/A"

    # Remote: job_is_remote is sometimes null; work_arrangement is more reliable.
    if job.get("job_is_remote") is True:
        remote = "Yes"
    elif job.get("work_arrangement"):
        remote = job["work_arrangement"]            # e.g. remote / hybrid / onsite
    else:
        remote = "No"

    employment = job.get("job_employment_type", "")
    posted = job.get("job_posted_at") or job.get("job_posted_at_datetime_utc") or "N/A"
    publisher = job.get("job_publisher", "")

    # Seniority / experience.
    seniority = job.get("seniority_level", "")
    exp = job.get("required_experience_years")
    exp_str = f"{exp}+ years" if exp else ""

    # Salary: this API gives min/max/period, not a ready-made string.
    lo, hi = job.get("job_min_salary"), job.get("job_max_salary")
    period = job.get("job_salary_period", "")
    if lo or hi:
        salary = f"{lo or '?'} - {hi or '?'}" + (f" / {period.lower()}" if period else "")
    else:
        salary = "Not specified"

    skills = job.get("required_technologies") or []
    apply_options = job.get("apply_options") or []
    reviews = job.get("employer_reviews") or []

    description = (job.get("job_description") or "").strip()
    if len(description) > 1500:
        description = description[:1500].rstrip() + " ..."

    highlights = job.get("job_highlights") or {}

    def fmt_section(name: str) -> str:
        items = highlights.get(name) or []
        if not items:
            return ""
        bullets = "\n".join(f"   - {x}" for x in items)
        return f"\n\n{name}:\n{bullets}"

    parts = [
        f"{title} — {company}",
        f"Location: {loc} | Remote: {remote}",
        f"Employment: {employment or 'N/A'} | Posted: {posted}",
        f"Salary: {salary}",
    ]
    level_bits = " | ".join(b for b in (seniority, exp_str) if b)
    if level_bits:
        parts.append(f"Level: {level_bits}")
    if skills:
        parts.append(f"Key skills: {', '.join(skills)}")
    if website:
        parts.append(f"Company site: {website}")
    if publisher:
        parts.append(f"Listed via: {publisher}")

    out = "\n".join(parts)

    out += fmt_section("Qualifications")
    out += fmt_section("Responsibilities")
    out += fmt_section("Benefits")

    if reviews:
        review_lines = []
        for r in reviews:
            score = r.get("score")
            if score is None:
                continue
            pub = r.get("publisher", "")
            cnt = r.get("review_count", "?")
            maxs = r.get("max_score", 5)
            review_lines.append(f"   - {pub}: {score}/{maxs} ({cnt} reviews)")
        if review_lines:
            out += "\n\nEmployer reviews:\n" + "\n".join(review_lines)

    if apply_options:
        opt_lines = [
            f"   - {o.get('publisher', 'Link')}: {o.get('apply_link', '')}"
            for o in apply_options[:5]
        ]
        out += "\n\nApply options:\n" + "\n".join(opt_lines)
    else:
        out += f"\n\nApply: {job.get('job_apply_link', 'N/A')}"

    if description:
        out += f"\n\nDescription:\n{description}"

    return out


tools = [
    get_weather,
    search_web,
    search_jobs,
    get_job_details,
    get_estimated_salary,
    get_company_salary,
    write_job_blog,
]
TOOLS_BY_NAME = {t.name: t for t in tools}

# These tools already return a clean, formatted, ready-to-read result. Their
# output is shown to the user directly (see print_stream) and the turn ends
# after they run (see after_tools) — so the model never re-summarizes a job
# list nor chains an unrequested get_job_details onto a search.
DISPLAY_TOOL_OUTPUT = {
    "search_jobs",
    "get_job_details",
    "get_estimated_salary",
    "get_company_salary",
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

# A plain model with NO tools bound — it can only write text, never call a tool,
# so it can't trigger another tool_use_failed glitch. Used to turn a salvaged
# raw tool result into a clean answer for the user. Runs on the smaller 8B
# model: summarizing doesn't need the 70B, and keeping it off 70B preserves
# that model's daily token budget for tool routing.
summarizer = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.3,
    groq_api_key=os.getenv("GROQ_API_KEY"),
)

def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"


def after_tools(state: AgentState) -> str:
    """Decide where to go after the tools node.
    Display tools (job list, job details, salary) already print their full
    result to the user, so end the turn. This also stops the model from chaining
    an unrequested get_job_details onto a search. Other tools (weather, web
    search) loop back so the model can compose a reply from their output."""
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


def salvage_failed_tool_call(error: BadRequestError) -> str | None:
    """Last-resort fallback: pull the mangled tool call out of Groq's error
    payload and run it manually. Returns the raw tool output (which is then
    handed to the summarizer so the user sees prose, not JSON)."""
    body = getattr(error, "body", None) or {}
    failed = body.get("error", {}).get("failed_generation", "")
    # Matches both <function=name{...} and <function=name,{...} variants.
    m = re.search(r"<function=(\w+).*?(\{.*\})", failed, re.DOTALL)
    if not m:
        return None
    name, raw_args = m.group(1), m.group(2)
    tool_fn = TOOLS_BY_NAME.get(name)
    if tool_fn is None:
        return None
    try:
        args = json.loads(raw_args)
        return tool_fn.invoke(args)
    except Exception:
        return None


def summarize_tool_result(query: str, raw_result: str) -> str:
    """Turn a raw tool result into a clean answer for the user."""
    prompt = [
        SystemMessage(content=(
            "You are Agent_J. The user asked a question and a tool returned "
            "raw results. Write a clear, concise answer based only on those "
            "results. Do not mention JSON, search, or tools. Cite the source links "
            "where useful."
        )),
        ("user", f"User's question: {query}\n\nTool results:\n{raw_result}"),
    ]
    return summarizer.invoke(prompt).content


def run_with_retry(inputs, max_attempts=4):
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
        except openai.APIError as e:
            # Auth/connection/other OpenRouter API errors. Report, don't crash.
            text = _provider_error_text(e) or str(e)
            print(
                "\nAgent_J: I couldn't reach the model just now (" + text +
                "). Please check your OPENROUTER_API_KEY / connection and try again.",
                flush=True,
            )
            return
        except RateLimitError as e:
            # Token/request quota hit — retrying immediately won't help, so tell
            # the user plainly (including the API's "try again in ..." hint).
            message = str(e)
            try:
                message = e.body.get("error", {}).get("message", message)
            except Exception:
                pass
            print(
                "\nAgent_J: I've hit the Groq rate limit, so I can't answer right "
                "now. " + message,
                flush=True,
            )
            return
        except BadRequestError as e:
            if "tool_use_failed" not in str(e):
                raise  # a real error — don't swallow it
            last_error = e
            if attempt < max_attempts:
                logger.debug(
                    "tool-call glitch, retrying %d/%d",
                    attempt,
                    max_attempts - 1,
                )

    # All retries exhausted — salvage the mangled call, then summarize it
    # into a proper answer instead of dumping raw JSON.
    salvaged = salvage_failed_tool_call(last_error)
    if salvaged is not None:
        query = inputs["messages"][-1][1]  # the user's question text
        print("\nAgent_J:\n\n" + summarize_tool_result(query, salvaged), flush=True)
    else:
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