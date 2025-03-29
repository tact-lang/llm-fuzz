# LLM-Fuzz

A smart fuzzing tool that leverages Large Language Models to systematically test the Tact compiler for the TON blockchain.

## Overview

LLM-Fuzz employs AI agents to intelligently fuzz test the Tact compiler by:

-   Testing edge cases and unusual code patterns
-   Comparing actual compiler behavior against documentation
-   Identifying bugs, crashes, and documentation mismatches
-   Generating minimal reproducible examples for each issue

## Installation

1. Clone this repository:

```bash
git clone https://github.com/tact-lang/llm-fuzz.git
cd llm-fuzz
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure you have the Tact compiler installed and available in your PATH.

4. Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

## Usage

Run the fuzzing tool:

```bash
python main.py
```

The tool will:

-   Launch 20 parallel LLM agents to test different aspects of the compiler
-   Log all activities and findings in real-time
-   Store successful code snippets in the `snippets/` directory
-   Track found issues in `found_issues.md`
-   Record reported issues in `reported_issues.md`

To stop the tool, press Ctrl+C in your terminal.

## How It Works

1. Each agent is initialized with comprehensive instructions to test specific Tact compiler features
2. Agents systematically craft test cases to explore edge cases and potential issues
3. Snippets are compiled with the actual Tact compiler to verify behavior
4. When an issue is found, it is automatically reported with a detailed explanation and minimal example
5. New agents are spawned to replace those that complete their tasks

## Key Files and Directories

-   `found_issues.md`: Documents already known but not yet resolved issues. This prevents agents from repeatedly reporting the same issues and helps focus testing efforts on undiscovered problems.
-   `reported_issues.md`: Records new issues discovered during test runs. Each report includes a detailed explanation, reproducible code, and documentation references.
-   `snippets/`: Contains all successfully compiled code snippets for reference and further analysis.
-   `tmp/`: Stores all temporary files generated during testing, including compilation artifacts and files that failed to compile.

## Configuration

Key configuration options (in `main.py`):

-   `MODEL_NAME`: The OpenAI model to use (default: "o3-mini")
-   `REASONING`: The reasoning effort level (default: "medium")
-   `num_agents`: Number of parallel agents to run (default: 20)

## Project Structure

-   `main.py`: Main fuzzing engine
-   `requirements.txt`: Python dependencies
-   `snippets/`: Successful code snippets
-   `tmp/`: Temporary files
-   `found_issues.md`: Documented issues
-   `reported_issues.md`: Issues reported by agents

## Scaling

This approach can be scaled in three dimensions:

-   **Horizontal**: Increase the number of parallel agents
-   **Vertical**: Use more advanced LLM models
-   **Depth**: Adjust prompts for deeper exploration of specific features

## Output

-   Console output provides real-time updates on agent activities
-   `snippets/` directory contains all successfully compiled test cases
-   `reported_issues.md` details all issues found with reproduction steps

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
