import os
import subprocess
import shutil
import json
import random
import string
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED

##############################################################################
#                            Constants & Configuration                       #
##############################################################################
from openai import OpenAI

MODEL_NAME = "o3-mini"
REASONING = {"effort": "medium"}
TOOL_CHOICE_STRATEGY = "required"
RUN_PREFIX_LENGTH = 8
FOUND_ISSUES_FILE = "found_issues.md"
REPORTED_ISSUES_FILE = "reported_issues.md"  # New file for reported issues

# Prompts (all messaging content as constants)
INITIAL_SYSTEM_PROMPT = """You are a highly specialized autonomous fuzz-testing agent rigorously validating the Tact compiler for the TON blockchain.

## 🔧 ENVIRONMENT

You are operating in a controlled environment designed for one purpose: to **detect and confirm real bugs** or **documentation mismatches** in the Tact language. You have access to the following tools:

- `file_search`: Retrieve relevant official Tact documentation sections by keyword or concept.
- `compile_snippet`: Compile a Tact code snippet and return the compiler’s raw output.
- `report_issue`: Submit a confirmed compiler bug or documentation mismatch. It must include a detailed report and an explicit `found_issue: true` flag.

## 🎯 OBJECTIVE

Your sole purpose is to act as an intelligent, relentless “thinking fuzzer.”
Your mission is to:

- Systematically **test the actual behavior** of the Tact compiler.
- Aggressively seek edge cases, inconsistencies, crashes, and contradictions.
- **Break things.** If you can’t break something, try harder — explore deeper combinations and hidden paths.
- Confirm whether the compiler adheres to or violates the documentation.

You must **continue fuzzing until you discover a real issue** and submit it using `report_issue(..., found_issue: true)`. Only then may you stop.

You may use `report_issue(..., found_issue: false)` **only if** you detect that something is broken in your own behavior (e.g., you're stuck in a loop, repeatedly retesting, or unable to progress meaningfully). This is for **malfunction handling only** — not for regular task completion.

## 🧪 ONE TEST AT A TIME — STRICT REQUIREMENT

Each compilation must test **exactly one** concept, rule, or hypothesis.

- Do NOT combine unrelated features, multiple functions, or multiple contracts in a single compilation.
- Test all edge cases **individually and iteratively**, not in bulk.
- Every test must be **minimal**, **precise**, and **unambiguous**.

## 🧩 FUNCTION INCLUSION RULE — DON’T TEST UNUSED CODE

If you are testing a function, it must be **referenced from a contract** — or it will not be compiled at all.

For example, this function will **not be fully compiled**:

```tact
fun test(): Int {{
    return 123;
}}
```

But this **will** be compiled fully:

```tact
fun test(): Int {{
    return 123;
}}

contract TestContract {{
    receive() {{
        test();
    }}
}}
```

If a function is not used inside a contract (usually in a receiver), the compiler may skip it entirely.
**You must ensure that every function you are testing is actually compiled.**

## ❌ REPORTING RULES (NON-NEGOTIABLE)

Use `report_issue` **only when** you have a confirmed, serious issue.

✅ Valid report criteria:
- A **compiler bug**: crash, silent miscompilation, invalid diagnostics, or incorrect output.
- A **documentation mismatch**: when the official documentation contradicts actual compiler behavior.

### 📋 EVERY REPORT MUST INCLUDE:

- ✅ A **minimal reproducible code snippet**.
- ✅ The **expected behavior**, based on documentation.
- ✅ The **actual compiler behavior** (output).
- ✅ A clear explanation of why the behavior is incorrect.
- ✅ A **direct citation from the documentation** (quote or summarize clearly).

All five elements are **mandatory**. If any are missing, the report is invalid.

## 🚫 DUPLICATE REPORTING IS STRICTLY FORBIDDEN

- You may only report each unique issue **once**.
- If you encounter the same bug again in a different test case, **do not report it again**.
- Variants of the same core problem still count as one issue.
- Duplicate reports are prohibited and considered a mission failure.

## 🚷 FORBIDDEN BEHAVIOR

- Do NOT re-test or re-report any issue listed in `{found_issues}`.
- Do NOT make assumptions — always verify via compilation.
- Do NOT summarize or conclude with non-issues.
- Do NOT repeat findings.
- Do NOT use `report_issue(..., found_issue: false)` as a clean exit — it is for **malfunctions only**.

## 📌 YOUR MINDSET

- You are a detector — not a narrator, not a summarizer.
- You work in silence unless something is broken.
- You never stop until a bug or contradiction is found.
- You submit **one full, unique, and verified report**.
- You never test unused functions or unreachable code.
- You isolate and test **exactly one behavior per snippet**, iterating as needed.

The only thing that matters is surfacing real, **unique**, **complete**, and **verifiable** issues — each one backed by documentation and supported by minimal, precise test code.

---

## ✅ KNOWN ISSUES

The following issues have already been reported and fully confirmed.
They must not be tested, re-reported, or mentioned again under any circumstances:

{found_issues}"""

INITIAL_USER_MESSAGE = """Begin your fuzz-testing cycle by focusing exclusively on the behavior of the `initOf` and `codeOf` expressions in Tact.

These expressions are used to obtain the init or code cell of a contract.

Your goal is to:

- Verify that the compiler behavior matches the documentation when using `initOf Contract` and `codeOf Contract`
- Confirm that these expressions work correctly with different contracts and parameters (if supported)
- Test edge cases such as:
    - Passing non-contract types
    - Using undefined contract types
    - Contracts with unusual structure or init parameters
- Identify any misleading or unclear compiler diagnostics
- Detect any undocumented limitations or behaviors

Test 3–4 cases per feature, then move on.

Focus only on `initOf` and `codeOf` in this session."""

CONTINUATION_USER_MESSAGE = (
    "Continue your fuzz-testing process rigorously and systematically. "
    "Persist deeply and exhaustively exploring each compiler feature, ensuring thorough testing of subtle, tricky, and non-obvious edge cases. "
    "Always strictly avoid repeating tests or reporting known documented issues—these are fully acknowledged and require no further validation. "
    "You MUST NOT stop your exploration prematurely—keep going until you explicitly confirm a significant compiler bug or documentation mismatch. "
    "Keep going!"
)

REPORT_PROMPT_TEMPLATE = """You have detected a potential severe issue or misinformation. Immediately invoke the 'report_issue' command with this detailed reason: {reason}"""

BUG_REASON_TEMPLATE = """Compilation of snippet '{snippet_id}' uncovered a critical anomaly:
--- Begin Compiler Output ---
{output}
--- End Compiler Output ---

Carefully review the above compiler output to confirm this significant bug or documentation issue before invoking 'report_issue'."""

##############################################################################
#                                Logging & Colors                            #
##############################################################################

COLORS = {
    "blue": "\033[94m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "reset": "\033[0m",
}


def log_info(message: str, agent_id=None):
    prefix = f"[Agent {agent_id}] " if agent_id is not None else ""
    print(f"{COLORS['blue']}[INFO]{COLORS['reset']} {prefix}{message}")


def log_success(message: str, agent_id=None):
    prefix = f"[Agent {agent_id}] " if agent_id is not None else ""
    print(f"{COLORS['green']}[SUCCESS] ✅{COLORS['reset']} {prefix}{message}")


def log_warning(message: str, agent_id=None):
    prefix = f"[Agent {agent_id}] " if agent_id is not None else ""
    print(f"{COLORS['yellow']}[WARNING]{COLORS['reset']} {prefix}{message}")


def log_error(message: str, agent_id=None):
    prefix = f"[Agent {agent_id}] " if agent_id is not None else ""
    print(f"{COLORS['red']}[ERROR] ❌{COLORS['reset']} {prefix}{message}")


##############################################################################
#                              Helper Functions                              #
##############################################################################


def truncate(text: str, length=200) -> str:
    """Truncates a string if it exceeds the specified length."""
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= length else text[:length] + "..."


def bug_found(output: str, succeeded: bool) -> bool:
    """
    Determine if the output indicates a bug.
    Flags a bug if:
      - The output contains "INTERNAL COMPILER ERROR" (case insensitive), OR
      - The compilation failed (non-zero exit) and the output does not contain "tact compilation failed".
    """
    output_lower = output.lower()
    if "internal compiler error" in output_lower:
        return True
    if not succeeded and "tact compilation failed" not in output_lower:
        return True
    return False


def compile_snippet(
    code: str, run_prefix: str, snippet_index: int, agent_id=None
) -> dict:
    """
    Compiles a Tact code snippet.
    Writes code to a file in 'tmp/', attempts to compile it, and if compilation succeeds,
    copies the file to 'snippets/'.
    Returns a dictionary with the compiler output and a flag indicating success.
    """
    filename = f"{run_prefix}_{snippet_index}.tact"
    tmp_file = os.path.join("tmp", filename)
    compiler_output_file = os.path.join("tmp", f"{run_prefix}_{snippet_index}.txt")
    snippets_dir = "snippets"
    snippet_destination = os.path.join(snippets_dir, filename)

    os.makedirs("tmp", exist_ok=True)
    os.makedirs(snippets_dir, exist_ok=True)

    log_info(f"Compiling snippet #{snippet_index} -> '{tmp_file}'", agent_id)
    with open(tmp_file, "w") as f:
        f.write(code)

    try:
        result = subprocess.run(
            ["tact", tmp_file],
            capture_output=True,
            text=True,
            check=True,
        )
        compiler_output = result.stdout
        compilation_succeeded = True
        shutil.copy(tmp_file, snippet_destination)
        log_success(
            f"Snippet compiled successfully. Copied '{snippet_destination}'.", agent_id
        )
    except subprocess.CalledProcessError as e:
        compiler_output = e.stderr
        compilation_succeeded = False
        log_warning("Snippet compilation failed, not copying to 'snippets/'", agent_id)

    with open(compiler_output_file, "w") as outf:
        outf.write(compiler_output)

    return {"output": compiler_output, "succeeded": compilation_succeeded}


##############################################################################
#                           Read Existing Found Issues                       #
##############################################################################

found_issues_markdown = "# Found Issues\n\n(None recorded yet.)"
if os.path.isfile(FOUND_ISSUES_FILE):
    with open(FOUND_ISSUES_FILE, "r") as f:
        found_issues_markdown = f.read()

##############################################################################
#                              Tools                                         #
##############################################################################

file_search_tool = {
    "type": "file_search",
    "vector_store_ids": ["vs_67e0f7d512908191a41628a474ab1f22"],
    "max_num_results": 10,
}

compile_snippet_tool = {
    "type": "function",
    "name": "compile_snippet",
    "description": (
        "Compiles a provided Tact source code snippet using the Tact compiler. "
        "You must supply the exact source code snippet you wish to test as input. "
        "The tool returns the exact, verbatim output produced by the compiler, "
        "including compilation success status, error messages, warnings, or internal errors."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "The complete Tact source code snippet to compile. "
                    "Ensure the snippet is concise, minimal, and specifically designed "
                    "to test or validate a documented claim or compiler behavior."
                ),
            }
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    "strict": True,
}

report_issue_tool = {
    "type": "function",
    "name": "report_issue",
    "description": "Use ONLY to report a CONFIRMED compiler bug or documentation mismatch. Include full reproduction details and set `found_issue` accordingly. Use `found_issue: false` ONLY if the agent itself is misbehaving.",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Full, detailed description of the confirmed issue. Must include a reproducible Tact snippet, expected vs. actual behavior, and a citation from the documentation.",
            },
            "found_issue": {
                "type": "boolean",
                "description": "`true` if you are reporting a confirmed compiler bug or documentation mismatch. `false` ONLY if you are malfunctioning or unable to continue.",
            },
        },
        "required": ["reason", "found_issue"],
        "additionalProperties": False,
    },
    "strict": True,
}

##############################################################################
#                   Conversation & Model Initialization                      #
##############################################################################

client = OpenAI()

final_system_prompt = INITIAL_SYSTEM_PROMPT.format(found_issues=found_issues_markdown)


##############################################################################
#                          Worker (Agent) Function                           #
##############################################################################


def run_agent(agent_id: int):
    """
    Each agent runs in its own thread, maintaining its own conversation with the model
    and handling compile_snippet / file_search / report_issue logic independently.
    When an agent calls 'report_issue', it logs the issue and then stops running.
    """
    # Create a unique run_prefix so snippet files don't collide
    random_part = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=RUN_PREFIX_LENGTH)
    )
    run_prefix = f"agent{agent_id}_{random_part}"

    # Track all snippet file paths this agent tried to compile
    compiled_snippets = []

    # Build the initial conversation for this agent
    response = client.responses.create(
        model=MODEL_NAME,
        reasoning=REASONING,
        input=[
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": INITIAL_USER_MESSAGE},
        ],
        tools=[compile_snippet_tool, file_search_tool, report_issue_tool],
        store=True,
        tool_choice=TOOL_CHOICE_STRATEGY,
    )

    log_info("Initial response received.", agent_id=agent_id)
    snippet_index = 0

    while True:
        items = response.output

        # If there are no output items, prompt the agent to continue
        if not items:
            response = client.responses.create(
                model=MODEL_NAME,
                reasoning=REASONING,
                previous_response_id=response.id,
                input=[{"role": "user", "content": CONTINUATION_USER_MESSAGE}],
                tools=[compile_snippet_tool, file_search_tool, report_issue_tool],
                store=True,
                tool_choice=TOOL_CHOICE_STRATEGY,
            )
            continue

        function_call_handled = False
        for idx, item in enumerate(items):
            if item.type == "function_call":
                if item.name == "compile_snippet":
                    # Parse the snippet code
                    try:
                        args = json.loads(item.arguments)
                    except json.JSONDecodeError:
                        log_error(
                            "Could not parse compile_snippet arguments.", agent_id
                        )
                        continue

                    code_snippet = args.get("code", "")
                    snippet_index += 1

                    # Compile the snippet
                    result = compile_snippet(
                        code_snippet, run_prefix, snippet_index, agent_id
                    )
                    compiler_result = result["output"]
                    succeeded = result["succeeded"]

                    # Record the snippet path attempted
                    filename = f"{run_prefix}_{snippet_index}.tact"
                    tmp_file = os.path.join("tmp", filename)
                    snippet_destination = os.path.join("snippets", filename)
                    snippet_path = snippet_destination if succeeded else tmp_file
                    compiled_snippets.append(snippet_path)

                    # Return the compiler result as a function_call_output
                    function_call_output = {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": compiler_result,
                    }

                    # If we suspect a bug, feed the relevant user prompt
                    additional_messages = []
                    if bug_found(compiler_result, succeeded):
                        log_warning(
                            "Potential bug discovered in compiler output.", agent_id
                        )
                        bug_reason = BUG_REASON_TEMPLATE.format(
                            snippet_id=f"{run_prefix}_{snippet_index}",
                            output=truncate(compiler_result),
                        )
                        additional_messages.append(
                            {
                                "role": "user",
                                "content": REPORT_PROMPT_TEMPLATE.format(
                                    reason=bug_reason
                                ),
                            }
                        )

                    # Send the function_call_output plus any extra messages back
                    response = client.responses.create(
                        model=MODEL_NAME,
                        reasoning=REASONING,
                        previous_response_id=response.id,
                        input=[function_call_output] + additional_messages,
                        tools=[
                            compile_snippet_tool,
                            file_search_tool,
                            report_issue_tool,
                        ],
                        store=True,
                        tool_choice=TOOL_CHOICE_STRATEGY,
                    )
                    function_call_handled = True
                    break

                elif item.name == "report_issue":
                    # Handle the report_issue function: log and optionally record the reported issue
                    try:
                        report_args = json.loads(item.arguments)
                    except json.JSONDecodeError:
                        report_args = {
                            "reason": "No reason provided due to JSON error.",
                            "found_issue": False,
                        }
                    reason = report_args.get("reason", "No reason provided")
                    found_issue = report_args.get("found_issue", False)
                    log_warning(
                        f"REPORT_ISSUE function called. Issue: {reason}", agent_id
                    )

                    # Format the compiled snippet paths as clickable markdown links
                    if compiled_snippets:
                        formatted_snippets = "\n".join(
                            [
                                f"- [{os.path.basename(path)}]({path})"
                                for path in compiled_snippets
                            ]
                        )
                    else:
                        formatted_snippets = (
                            "No code snippets compiled in this session."
                        )

                    # --- Extract cited documentation filenames from response messages ---
                    cited_files = set()
                    for resp_item in response.output:
                        if resp_item.type == "message" and isinstance(
                            resp_item.content, list
                        ):
                            for element in resp_item.content:
                                if (
                                    isinstance(element, dict)
                                    and "annotations" in element
                                ):
                                    for annotation in element["annotations"]:
                                        if annotation.get("type") == "file_citation":
                                            cited_files.add(annotation.get("filename"))
                    if cited_files:
                        citations_markdown = "\n".join(
                            [f"- {filename}" for filename in sorted(cited_files)]
                        )
                    else:
                        citations_markdown = "No cited documentation files."

                    report_message = (
                        f"\n\n## Reported Issue by Agent {agent_id}\n\n"
                        f"**Issue:**\n{reason}\n\n"
                        f"**Compiled Code Snippets:**\n{formatted_snippets}\n\n"
                        f"**Cited Documentation Files:**\n{citations_markdown}\n\n"
                    )

                    # Write the report only if found_issue is True.
                    if found_issue:
                        with open(REPORTED_ISSUES_FILE, "a") as f:
                            f.write(report_message)
                        log_info("Issue logged to reported issues file.", agent_id)
                    else:
                        log_info(
                            "found_issue is false; not logging the issue report.",
                            agent_id,
                        )

                    # Return a confirmation to the agent with 2 newlines before and after the message
                    function_call_output = {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": "\n\nIssue reported. Stopping agent.\n\n",
                    }
                    response = client.responses.create(
                        model=MODEL_NAME,
                        reasoning=REASONING,
                        previous_response_id=response.id,
                        input=[function_call_output],
                        tools=[
                            compile_snippet_tool,
                            file_search_tool,
                            report_issue_tool,
                        ],
                        store=True,
                        tool_choice=TOOL_CHOICE_STRATEGY,
                    )
                    # Stop the agent if found_issue is true.
                    if found_issue:
                        return
                    else:
                        # Add user message saying that agent should continue fuzzing until it finds an issue.
                        response = client.responses.create(
                            model=MODEL_NAME,
                            reasoning=REASONING,
                            previous_response_id=response.id,
                            input=[
                                {"role": "user", "content": CONTINUATION_USER_MESSAGE}
                            ],
                            tools=[
                                compile_snippet_tool,
                                file_search_tool,
                                report_issue_tool,
                            ],
                            store=True,
                            tool_choice=TOOL_CHOICE_STRATEGY,
                        )
                        break

                else:
                    log_warning(f"Unknown function called: {item.name}", agent_id)

            elif item.type == "message":
                # Safely attempt to extract text
                message_text = item.content
                if not isinstance(message_text, str):
                    if hasattr(message_text, "text"):
                        message_text = message_text.text
                    elif (
                        isinstance(message_text, list)
                        and len(message_text) > 0
                        and hasattr(message_text[0], "text")
                    ):
                        message_text = message_text[0].text
                    else:
                        message_text = str(message_text)

                truncated_content = truncate(message_text)
                log_info(f"Agent text message: {truncated_content}", agent_id)

            elif item.type == "file_search_call":
                log_info("🔎 The agent is searching the Tact docs.", agent_id)

            elif item.type == "reasoning":
                log_info("💭 The agent is thinking.", agent_id)

            else:
                log_info(f"Other item => {truncate(str(item))}", agent_id)

        # If no function call was handled, prompt the agent to continue with the next step of fuzzing:
        if not function_call_handled:
            response = client.responses.create(
                model=MODEL_NAME,
                reasoning=REASONING,
                previous_response_id=response.id,
                input=[{"role": "user", "content": CONTINUATION_USER_MESSAGE}],
                tools=[compile_snippet_tool, file_search_tool, report_issue_tool],
                store=True,
                tool_choice=TOOL_CHOICE_STRATEGY,
            )


##############################################################################
#                          Main Thread + Respawning                          #
##############################################################################


def main():
    # We keep 20 agents running at all times, spawning a new one whenever one finishes.
    num_agents = 20

    # A function to spawn an agent with a new ID
    agent_counter = 0

    with ThreadPoolExecutor(max_workers=num_agents) as executor:
        # Submit the first 20 agents
        futures = []
        for _ in range(num_agents):
            agent_counter += 1
            f = executor.submit(run_agent, agent_counter)
            futures.append(f)

        try:
            while True:
                # Wait for any agent to finish
                done, not_done = concurrent.futures.wait(
                    futures, return_when=FIRST_COMPLETED
                )

                # For each agent that finished, spawn a new one
                for d in done:
                    futures.remove(d)
                    # The agent ended, so let's spawn a replacement
                    agent_counter += 1
                    new_future = executor.submit(run_agent, agent_counter)
                    futures.append(new_future)

                # To avoid CPU spinning, sleep briefly
                time.sleep(1)

        except KeyboardInterrupt:
            log_warning(
                "Keyboard interrupt detected. Shutting down fuzzing now.",
                agent_id="MAIN",
            )

    log_info("All agents have been terminated (main thread is exiting).")


if __name__ == "__main__":
    main()
