## Proposal: Leveraging LLM-Based Smart Fuzzing for Tact Compiler

### Core Idea

The core idea is to leverage Large Language Models (LLMs) to perform "smart fuzzing" of the Tact compiler by directly utilizing its official documentation. By providing LLMs with real-time access to detailed documentation via Retrieval-Augmented Generation (RAG), the agents intelligently and systematically identify issues such as internal compiler errors and mismatches between compiler behavior and specification.

### Industry Context

Similar experiments utilizing LLM-driven fuzzing have demonstrated substantial success in leading organizations, including Google's OSS-Fuzz initiative and academic research such as WhiteFox (OOPSLA 2024) and PromptFuzz (CCS 2024). As LLMs become increasingly intelligent and agentic, this approach is gaining traction, offering a novel method for efficiently uncovering subtle bugs and inconsistencies that traditional fuzzing methods might miss.

### Current Results

In a preliminary test conducted with an $100 API budget using the o3-mini model:

-   **10 issues** were identified quickly: 2 minor compiler bugs, 2 duplicates of known but unresolved bugs, and 6 mismatches between documentation and actual compiler implementation.
-   **False Positive Rate:** Approximately 33% (5 false positives apart from 10 valid findings). This rate is relatively low given the rapid, one-day implementation and can be further improved through careful tuning and validation mechanisms.

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

To scale this experiment effectively, I am proposing a phased approach:

-   **Phase 1: Experimental Budget**

    -   Requesting an initial budget of **$1,000** to support further experimentation.
    -   This phase will include many small-to-medium runs using different models (e.g., o3-mini, GPT-4, Claude Sonnet) and varying pipeline/prompt setups.
    -   Goal: evaluate cost-to-findings ratio, optimize pipeline design, and choose the most efficient configuration for scaling.
    -   Expected side benefit: uncovering more issues during experimentation.

-   **Phase 2: Scaled Run of Optimized Setup**

    -   Using the most effective configuration discovered in Phase 1, we scale the experiment to a **$5,000** budget.
    -   Objective: analyze how effectiveness changes with budget and run size, assess limits of horizontal/depth scaling, and gather larger sample of findings.

-   **Phase 3: Long-Term Strategy Evaluation**
    -   Based on Phase 2 results, we can define the most efficient way to integrate the system into our development process. Options include:
        -   Periodic medium-to-large runs tied to compiler releases.
        -   Lightweight daily/weekly runs to catch regressions.
        -   Full CI integration for all compiler PRs to detect real-time issues, documentation mismatches, or edge-case regressions.

This phased approach allows for cost-efficient exploration, scalable evaluation, and practical integration tailored to TON Studio’s needs.

### Conclusion

This approach offers a powerful, innovative, and scalable method for improving compiler reliability and documentation accuracy, aligning well with TON Studio's strategic goals. With minimal upfront investment and clear scaling paths, integrating LLM-driven smart fuzzing into the development workflow can significantly enhance Tact compiler quality and maintainability.
