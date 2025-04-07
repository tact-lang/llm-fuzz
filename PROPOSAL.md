## Proposal: Leveraging LLM-Based Smart Fuzzing for Tact Compiler

### Core Idea

The core idea is to leverage Large Language Models (LLMs) to perform "smart fuzzing" of the Tact compiler by directly utilizing its official documentation. By providing LLMs with real-time access to detailed documentation via Retrieval-Augmented Generation (RAG), the agents intelligently and systematically identify issues such as internal compiler errors and mismatches between compiler behavior and specification.

### Industry Context

Similar experiments utilizing LLM-driven fuzzing have demonstrated substantial success in leading organizations, including Google's OSS-Fuzz initiative and academic research such as WhiteFox (OOPSLA 2024) and PromptFuzz (CCS 2024). As LLMs become increasingly intelligent and agentic, this approach is gaining traction, offering a novel method for efficiently uncovering subtle bugs and inconsistencies that traditional fuzzing methods might miss.

### Current Results

In a preliminary test conducted with **5,000 LLM requests** (**~100 million** tokens processed, **$100** in costs) using the **o3-mini** model:

-   **10 issues** were identified quickly: 2 minor compiler bugs, 2 duplicates of known but unresolved bugs, and 6 mismatches between documentation and actual implementation.
-   **False Positive Rate:** ~33% (5 false positives out of 15 reported findings).

This was achieved with a small-scale, one-day pipeline and can be significantly improved with better agent structure and prompt engineering.

### Scaling Dimensions

The proposed approach can be effectively scaled in three dimensions:

-   **Horizontal Scaling:** Increasing the number of parallel agents running simultaneously. This is practically unlimited but proportionally increases the human oversight required for validating findings.
-   **Vertical Scaling:** Utilizing more advanced, intelligent LLMs to improve accuracy, reduce false positives, but at a higher API cost.
-   **Depth Scaling:** Adjusting the fuzzing pipeline and prompts to enable deeper exploration of specific compiler features. This encourages agents to spend more effort and iterations on particular cases, increasing the likelihood of uncovering complex issues but also raising operational costs and extending run durations.

This approach can be effectively scaled as extensively as desired, limited primarily by available human resources for validation and resolution of findings.

### Workflow Integration

There are several effective ways to integrate this fuzzing approach into our development workflow:

-   **One-time Run:** Conducting intensive, one-time fuzzing sessions with a fixed budget to perform comprehensive validation.
-   **Regular Scheduled Runs:** Running smaller, regular fuzzing sessions, such as weekly or aligned with new compiler releases, to continuously verify and maintain compiler integrity.
-   **PR-based Integration:** The most complex and innovative method involves integrating fuzzing directly into the Pull Request (PR) process. This would proactively identify:
    -   Issues in new features or bugfixes.
    -   Mismatches between implementation and proposed documentation.
    -   Edge cases from interactions between the new feature or bugfix and other parts of the codebase.

### Funding Estimates

To scale this experiment effectively, I propose a phased approach:

#### Phase 1: Experimental Setup (40–50k requests, ~800–1000M tokens)

-   Run multiple small-to-medium fuzzing loops.
-   Test different models (o3-mini, Claude Sonnet, GPT-4).
-   Optimize prompt engineering, the data pipeline, and issue validation logic.
-   Expectation: uncover dozens of new issues and build baseline metrics for cost-effectiveness.

#### Phase 2: Scaled Execution (400–500k requests, ~8–10B tokens)

-   Use the best-performing pipeline from Phase 1.
-   Run large-scale fuzzing campaigns.
-   Discover more issues, gather more metrics, and extract deeper insights.

#### Phase 3: Integration Pilot (TBD requests, based on results)

-   Based on insights from Phase 2, experiment with:
    -   Periodic medium-to-large runs tied to compiler releases.
    -   Lightweight daily/weekly runs to catch regressions.
    -   Full CI integration for all compiler PRs to detect real-time issues, documentation mismatches, or edge-case regressions.

---

### Cost Summary

| Phase                   | Requests | Tokens (est.) | Estimated Cost |
| ----------------------- | -------- | ------------- | -------------- |
| Phase 1                 | 50,000   | 1B            | ~$1,000        |
| Phase 2                 | 500,000  | 10B           | ~$10,000       |
| Integration Pilot (TBD) | TBD      | TBD           | TBD            |

> **Total requested budget: ~$11,000**  
> Covers ~550k requests across different models.  
> This enables thorough experimentation and a large-scale run.
