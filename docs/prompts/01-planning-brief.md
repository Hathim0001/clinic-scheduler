<!-- Prompt 3 in PROMPTS.md. Transcribed verbatim from the session by the assistant; compare it with
     the original text if in doubt. Nothing below this comment has been edited. -->

# MASTER PROMPT: ANALYZE BOTH PDFS AND GENERATE AN IMPLEMENTATION-READY HACKATHON PLAN.MD

## 1. ROLE AND OBJECTIVE

Act as a multidisciplinary expert team comprising:

- Principal Software Architect
- Senior Full-Stack Engineer
- AI/ML Engineer, where applicable
- Data Engineer
- Cybersecurity Engineer
- DevOps and Site Reliability Engineer
- Product Manager
- UX/UI Researcher
- Business and Innovation Strategist
- Technical Hackathon Mentor
- Hackathon Judging and Demonstration Specialist

Your mission is to thoroughly read, analyze, and cross-reference the **two PDF documents in the current project folder**, then create a comprehensive, technically rigorous, sponsor-aligned, implementation-ready `plan.md` file.

The deliverable must serve as the team's primary blueprint for designing, implementing, testing, deploying, demonstrating, and scaling the hackathon solution.

This is not a generic project proposal. Every major recommendation must connect to the actual problem statement, sponsor objectives, user needs, technical constraints, evaluation criteria, or a clearly identified engineering requirement.

The plan must address:

1. The exact problem described in the source documents.
2. The sponsor's specific business or operational needs.
3. Every explicit feature and requirement in the problem statement.
4. The target users and their real-world context.
5. Existing solutions and their documented limitations.
6. The proposed solution and unique value proposition.
7. Genuine innovation and defensible differentiation.
8. Complete technical architecture and implementation details.
9. Data modeling, algorithms, APIs, and integrations.
10. Security, privacy, accessibility, and responsible design.
11. Performance, reliability, scalability, and cost.
12. Software development lifecycle and CI/CD.
13. A realistic hackathon execution plan.
14. Measurable impact and a reproducible live demonstration.
15. A credible path from prototype to sponsor adoption and production.

**Primary principle:** Solve the sponsor's actual problem, validate the riskiest assumptions early, build a complete working end-to-end flow before expanding scope, prove claims with evidence, and make adoption believable.

Do not invent a solution before analyzing the PDFs.

---

# PHASE 1: SOURCE DOCUMENT DISCOVERY AND COMPLETE READING

## 2. Locate and inspect both PDFs

Identify the two PDF files in the current project folder.

For each document, record:

- Filename.
- Document title, if available.
- Page count.
- File size, if available.
- Relevant sections and appendices.

Read both PDFs completely, page by page, in their entirety.

Examine:

- Problem statements.
- Sponsor descriptions.
- Objectives.
- Functional requirements.
- Non-functional requirements.
- Constraints.
- Tables.
- Figures.
- Architecture diagrams.
- Workflow illustrations.
- Evaluation criteria.
- Judging rubrics.
- Expected deliverables.
- Appendices and footnotes.
- Any relevant implementation or technology guidance.

If text extraction fails to capture a diagram, table, scanned page, or other important visual content, use available OCR or visual inspection capabilities.

Cross-reference both documents to identify overlapping requirements, complementary information, contradictions, missing details, and ambiguities.

Never claim that a document was completely read unless every page has actually been processed.

If a PDF is missing, corrupted, or inaccessible, report the limitation honestly. Continue only with the available material and clearly identify the resulting gaps.

## 3. Establish source-grounded facts

Maintain a clear distinction between:

- Facts explicitly stated in the PDFs.
- Information obtained from credible external research.
- Reasonable interpretations.
- Engineering recommendations.
- Assumptions requiring validation.
- Proposed innovations.
- Capabilities that have not yet been implemented or tested.

Record the source filename and page number for important requirements and factual claims whenever possible.

Treat the source documents as the primary authority for the problem statement and explicit requirements.

Do not replace the sponsor's actual problem with a broader theme or an unrelated technology-driven idea.

---

# PHASE 2: SPONSOR ALIGNMENT AND PROBLEM SIGNIFICANCE

## 4. Identify the sponsor's actual problem

Extract the sponsor's documented business objectives, operational difficulties, target stakeholders, constraints, expected outcomes, and existing workflows.

Clearly distinguish:

1. The hackathon theme.
2. The sponsor's specific problem statement.
3. The underlying business or operational problem.
4. The affected users and stakeholders.
5. The measurable outcome the sponsor wants to improve.
6. The capabilities required to solve the problem.
7. The constraints imposed by the sponsor's environment.

Explain what the sponsor needs to achieve and why the problem matters.

Avoid generic descriptions such as "improve efficiency" or "use AI to automate the process" without explaining the underlying mechanism and measurable benefit.

## 5. Problem analysis

Document:

- What problem exists.
- Who experiences it.
- When and where it occurs.
- How the current process works.
- The root causes.
- The consequences of the problem.
- The cost of leaving it unresolved.
- Current inefficiencies, errors, delays, or barriers.
- Why existing approaches may be inadequate.
- Which assumptions remain unverified.
- Why the problem deserves attention.

Identify the smallest specific problem that the proposed MVP can solve convincingly.

Explain how the solution addresses the root causes rather than merely treating visible symptoms.

## 6. Target users and stakeholders

Identify primary users, secondary users, administrators, operators, and relevant sponsor stakeholders.

For each group, document:

- Goals.
- Context of use.
- Current workflow.
- Pain points.
- Technical proficiency.
- Accessibility requirements.
- Frequency of use.
- Adoption barriers.
- Expected benefits.
- Security and privacy concerns.

Create realistic user personas and user stories based on evidence or explicitly labeled assumptions.

Map the complete user journey from the initial problem to the desired outcome.

## 7. Sponsor alignment matrix

Create a table containing:

| Sponsor requirement | Business problem | Affected user | Proposed feature | Technical mechanism | Expected outcome | Success evidence |
|---|---|---|---|---|---|---|

Every mandatory feature must connect to a documented requirement or a clearly justified supporting capability.

Reject or defer features that add complexity without improving sponsor relevance, mandatory requirement coverage, demonstrable impact, or feasibility.

---

# PHASE 3: REQUIREMENT EXTRACTION AND TRACEABILITY

## 8. Create a complete requirement inventory

Before committing to an architecture, extract every explicit and reasonably implied requirement from both PDFs.

Use unique identifiers:

- FR-001: Functional requirements.
- NFR-001: Non-functional requirements.
- DATA-001: Data requirements.
- SEC-001: Security and privacy requirements.
- UX-001: UX and accessibility requirements.
- INT-001: Integration requirements.
- BIZ-001: Business requirements.
- EVAL-001: Evaluation requirements.
- CON-001: Constraints.
- OPS-001: Operational requirements.

For each requirement, record:

- ID.
- Requirement description.
- Source PDF and page.
- Business or user problem addressed.
- Proposed solution.
- Feature or component responsible.
- Implementation approach.
- Dependencies.
- Data requirements.
- Acceptance criteria.
- Verification method.
- Priority.
- Implementation phase.
- Demo evidence.

Prioritize requirements using:

- Must Have.
- Should Have.
- Could Have.
- Won't Have in the current release.

Mandatory source requirements must not be discarded simply because they are difficult to implement.

If full implementation is infeasible within the deadline, specify the feasible prototype, the remaining gap, and the production completion path.

## 9. Requirement traceability matrix

Map every requirement to:

- The proposed feature.
- The relevant architecture component.
- The API or workflow.
- The data model.
- The associated tests.
- The acceptance criteria.
- The live demonstration.
- The implementation milestone.

A requirement is not fully covered merely because it is mentioned in passing.

Identify missing, partial, blocked, or ambiguous requirements.

---

# PHASE 4: REAL-WORLD VALIDATION AND COMPETITIVE DIFFERENTIATION

## 10. Validate the problem with credible evidence

Identify evidence that establishes the existence, significance, and context of the problem.

Use available sources such as:

- The two PDFs.
- Peer-reviewed research.
- Official statistics.
- Government publications.
- Sponsor documentation.
- Industry reports.
- Reputable case studies.
- Official documentation for existing solutions.

If web research is available and relevant, research current existing solutions and cite the sources used.

Distinguish general industry evidence from evidence that the exact target users experience the specific problem.

Do not fabricate statistics, interviews, surveys, user feedback, or experimental results.

## 11. Real-world user research plan

Design a practical validation study.

Specify:

- Target participants.
- Recruitment approach.
- Interview questions.
- Survey questions, where useful.
- Existing workflow observation.
- Baseline measurements.
- Consent and privacy considerations.
- Data collection method.
- Analysis method.
- Sampling limitations.
- Evidence needed to support or reject the problem hypothesis.

Use open-ended questions that investigate actual past experiences rather than leading participants toward the proposed solution.

Identify the assumptions that should be validated before implementation begins.

If direct user research is impossible during the hackathon, use credible secondary evidence and transparent simulations. State what remains unvalidated.

## 12. Existing solutions and competitive analysis

Identify relevant:

- Direct competitors.
- Indirect competitors.
- Manual processes.
- Conventional software.
- Open-source tools.
- Commercial products.
- Sponsor's current workflow.
- Existing AI/ML approaches, where relevant.

Verify important claims using credible sources.

Create a comparison table:

| Dimension | Existing approach A | Existing approach B | Proposed solution |
|---|---|---|---|
| Core functionality | Verified capability | Verified capability | Proposed capability |
| Target users | Actual audience | Actual audience | Intended audience |
| Workflow | Existing process | Existing process | Improved process |
| Known limitations | Evidence-based | Evidence-based | Remaining limitations |
| Accuracy | Measured or unknown | Measured or unknown | Target and validation |
| Speed | Measured or unknown | Measured or unknown | Target and validation |
| Cost | Known or unknown | Known or unknown | Cost assumptions |
| Accessibility | Verified or unknown | Verified or unknown | Planned support |
| Privacy | Verified or unknown | Verified or unknown | Proposed controls |
| Reliability | Verified or unknown | Verified or unknown | Planned controls |

Use "Unknown" where evidence is unavailable.

Do not invent competitor limitations to make the proposed solution appear superior.

## 13. Identify the exact competitive gap

For each relevant existing approach, explain:

1. What it already does well.
2. What it fails to address.
3. Which users or scenarios remain underserved.
4. Why the gap exists, if evidence supports that conclusion.
5. Whether the gap is verified or hypothetical.
6. How the proposed implementation addresses it.
7. What measurable test can demonstrate improvement.

Distinguish among:

- Genuine technological novelty.
- A new combination of existing technologies.
- A better workflow.
- A targeted improvement for a specific user group.
- A contextual improvement over existing tools.

Never claim global uniqueness without adequate evidence.

## 14. Unique value proposition

Define a specific value proposition:

"For [target user] experiencing [specific problem], the product provides [measurable benefit] through [distinctive mechanism], unlike [existing alternative], which [verified limitation]."

Explain the mechanism, supporting evidence, expected benefit, measurement method, and limitations.

Provide different value propositions for different stakeholders when necessary.

---

# PHASE 5: PROPOSED SOLUTION AND INNOVATION

## 15. Proposed solution

Explain the complete solution, including:

- Core idea.
- Primary user journey.
- Main system behavior.
- Inputs and outputs.
- Business logic.
- Data processing.
- Integrations.
- Expected results.
- Error handling.
- User feedback.
- Operational requirements.

Create a problem-to-solution mapping:

| Problem | Root cause | Proposed capability | Technical mechanism | Expected benefit | Validation metric |
|---|---|---|---|---|---|

Every significant feature must solve a documented problem or fulfill a mandatory requirement.

## 16. Feature prioritization

Divide features into four tiers.

**Tier 1: Mandatory MVP**

All capabilities required to satisfy the explicit problem statement and demonstrate the core value proposition.

**Tier 2: High-value differentiators**

Features that address verified competitive gaps or meaningfully improve user outcomes.

**Tier 3: Optional enhancements**

Features added only after the core flow is working and tested.

**Tier 4: Post-hackathon roadmap**

Long-term production and business enhancements.

For each feature, specify:

- Feature ID.
- User problem.
- Requirement references.
- User story.
- Inputs and outputs.
- Implementation approach.
- Dependencies.
- Data requirements.
- Acceptance criteria.
- Tests.
- Failure cases.
- Estimated effort.
- MVP or later-release classification.

## 17. Innovation strategy

Identify a small number of meaningful, feasible, defensible innovations.

For every innovation, document:

1. Existing limitation.
2. Supporting evidence.
3. Target user need.
4. Proposed mechanism.
5. Algorithms or models involved.
6. Data requirements.
7. Integration dependencies.
8. Implementation effort.
9. Expected benefit.
10. Measurement method.
11. Failure modes.
12. Fallback.
13. Remaining limitations.
14. Competitive differentiation.

Do not add features merely to appear innovative.

Prioritize innovations that directly solve the sponsor's problem and can be implemented, tested, and demonstrated within the available time.

## 18. AI/ML decision

Use AI/ML only when it meaningfully improves the solution.

Compare AI/ML against appropriate alternatives such as:

- Deterministic rules.
- Search.
- Statistical methods.
- Conventional optimization.
- Traditional algorithms.
- Human-assisted workflows.

If AI/ML is appropriate, document:

- Model or model category.
- Input and output formats.
- Inference architecture.
- Data and evaluation requirements.
- Accuracy and quality metrics.
- Latency.
- Cost.
- Privacy.
- Failure detection.
- Hallucination or unsafe-output controls.
- Human review, where necessary.
- Fallback when the model or provider is unavailable.
- Model evaluation and update strategy.

If AI/ML is unnecessary, explain why a simpler approach is preferable.

---

# PHASE 6: RISKEST-ASSUMPTION-FIRST VALIDATION

## 19. Identify critical uncertainties

Identify the assumptions most likely to invalidate the solution.

Consider:

- Essential API availability.
- Sponsor system access.
- Dataset availability and quality.
- Third-party rate limits.
- Model performance.
- Algorithm correctness.
- Processing latency.
- User adoption.
- Permissions.
- External service costs.
- Hardware requirements.

For each assumption, record:

- Assumption ID.
- Description.
- Available evidence.
- Likelihood of being false.
- Impact if false.
- Validation experiment.
- Estimated duration.
- Resources needed.
- Pass/fail criteria.
- Alternative.
- Architectural implications.

## 20. Run the smallest useful validation experiment first

Identify the single riskiest assumption.

Design the smallest practical experiment capable of testing it before significant development effort is committed.

Examples include:

- Calling a critical API with a representative request.
- Validating access to a required dataset.
- Running the core algorithm on representative inputs.
- Benchmarking a candidate model.
- Measuring inference latency.
- Testing a small user workflow.
- Verifying a deployment dependency.

Define decision gates:

- Pass: continue with the preferred implementation.
- Partial pass: continue with a reduced scope or explicit limitation.
- Fail: switch to the fallback or revise the design.

Include a risk-first schedule in the roadmap.

Never spend most of the hackathon building around an unverified dependency.

---

# PHASE 7: END-TO-END MVP IMPLEMENTATION

## 21. Build one complete working flow first

Identify the single most important user journey that delivers the product's primary value.

Define its entire lifecycle:

1. User initiates an action.
2. Frontend validates the input.
3. Backend authenticates and authorizes the request.
4. Business logic validates the request.
5. Required data is retrieved.
6. Algorithms, models, or integrations execute.
7. The output is validated.
8. Data is persisted where required.
9. A response is returned.
10. The user receives an understandable result.
11. Relevant logs, metrics, and audit records are produced.
12. Failures are handled safely.

For every step, specify the component, input, output, dependency, error behavior, and test.

Use a vertical-slice development approach: implement one feature across frontend, backend, persistence, integration, testing, and deployment before expanding scope.

Recommended implementation order:

1. Validate the riskiest assumption.
2. Establish the development environment.
3. Define the critical data model and API contract.
4. Implement the main business logic.
5. Build the frontend interaction.
6. Integrate persistence and required services.
7. Complete the end-to-end happy path.
8. Add validation and authorization.
9. Test the complete workflow.
10. Deploy the working flow.
11. Add critical failure handling.
12. Demonstrate the primary value.
13. Expand scope only after acceptance tests pass.

## 22. Define the MVP completion gate

The MVP is complete only when:

- At least one complete primary user journey works.
- Essential business logic executes.
- Representative inputs produce correct outputs.
- Required data is persisted.
- Essential integrations work or an explicitly disclosed fallback is used.
- Automated tests verify critical behavior.
- Meaningful error handling exists.
- The demonstration is reproducible.
- Mandatory requirements have traceable implementation paths.

Do not confuse disconnected UI screens, mocked API responses, or static demonstrations with a fully functioning end-to-end product.

Clearly identify what is real, mocked, simulated, proposed, or untested.

---

# PHASE 8: TECHNICAL ARCHITECTURE

## 23. System architecture

Design a complete architecture appropriate to the requirements and deadline.

Consider relevant components:

- Frontend.
- Backend application.
- API layer.
- Authentication and authorization.
- Business logic.
- Database.
- File storage.
- Search and indexing.
- Cache.
- Background jobs.
- Message queues.
- External services.
- AI/ML inference.
- Analytics.
- Administration.
- Logging and monitoring.

Avoid unnecessary infrastructure and microservices.

Provide Mermaid diagrams for:

1. High-level system architecture.
2. Component interactions.
3. Data flow.
4. Primary request sequence.
5. Critical workflows.
6. Deployment architecture.
7. CI/CD pipeline.
8. Authentication or authorization flow, where relevant.
9. Asynchronous processing, where relevant.

Ensure the diagrams are syntactically valid and match the written design.

## 24. Technology stack

Select one primary stack rather than leaving the team with an undecided list of options.

Specify and justify:

- Frontend framework.
- Backend language and framework.
- API technology.
- Database.
- Authentication.
- Cache.
- Messaging, if needed.
- AI/ML framework, if needed.
- Cloud platform.
- Containerization.
- Testing tools.
- CI/CD platform.
- Monitoring tools.

For every major technology, explain its purpose, benefits, trade-offs, alternatives, and suitability for the deadline.

Prioritize implementation speed, maintainability, security, and a credible production path.

## 25. Architecture decision records

Document major decisions in ADR format:

- Context.
- Problem.
- Alternatives.
- Selected approach.
- Rationale.
- Advantages.
- Disadvantages.
- Security implications.
- Performance and cost implications.
- Failure modes.
- Conditions for reconsideration.

Explicitly consider:

- Monolith versus microservices.
- Relational versus non-relational database.
- Synchronous versus asynchronous processing.
- Managed services versus self-hosted infrastructure.
- Rules-based versus AI/ML approaches.
- Strong versus eventual consistency, where relevant.

For each decision, explain why the selected approach works for this specific use case.

---

# PHASE 9: IMPLEMENTATION, ALGORITHMS, AND APIs

## 26. Feature-level technical specifications

For each mandatory feature, provide:

- Purpose.
- User story.
- Preconditions.
- Main workflow.
- Alternative workflows.
- Inputs and outputs.
- Business rules.
- Frontend responsibilities.
- Backend responsibilities.
- APIs or events.
- Database entities.
- Validation.
- Permissions.
- Error handling.
- Edge cases.
- Logging.
- Metrics.
- Tests.
- Acceptance criteria.

## 27. Algorithms and processing logic

For every significant algorithm, describe:

- The problem being solved.
- Inputs and outputs.
- Processing steps.
- Pseudocode.
- Relevant mathematical or logical formulation.
- Time and space complexity where meaningful.
- Why the algorithm fits the use case.
- Alternatives considered.
- Accuracy or correctness considerations.
- Edge cases.
- Failure modes.
- Validation strategy.

Include a small representative worked example for nontrivial algorithms when it clarifies the implementation.

Explain the actual data flow from user input through processing, persistence, and final output.

## 28. API contracts

For each endpoint, specify:

- HTTP method.
- Route.
- Purpose.
- Authentication.
- Authorization.
- Request schema.
- Response schema.
- Validation rules.
- Status codes.
- Error format.
- Pagination.
- Filtering.
- Rate limits.
- Timeouts.
- Retry policies.
- Idempotency.
- Versioning.
- Logging and monitoring.

Include representative request and response examples.

For asynchronous operations, define submission, status checking, completion, and failure behavior.

Handle duplicate requests and partial failures safely. Never blindly retry non-idempotent operations.

---

# PHASE 10: DATA MODEL AND DATA QUALITY

## 29. Database design

Define:

- Core entities.
- Attributes and types.
- Primary keys.
- Foreign keys.
- Relationships and cardinality.
- Constraints.
- Indexes.
- Normalization.
- Denormalization where justified.
- Audit fields.
- Data lifecycle.
- Retention.
- Soft deletion where appropriate.
- Migrations.
- Backup and restoration.

Provide a Mermaid ER diagram and representative SQL DDL or equivalent schema definitions.

Explain how each entity supports the required features.

## 30. Data quality and persistence

Document:

- Data sources.
- Licensing.
- Provenance.
- Input validation.
- Missing values.
- Duplicates.
- Stale records.
- Inconsistent records.
- Data corruption.
- Schema evolution.
- Data reconciliation.
- Sensitive data classification.
- Encryption.
- Access control.
- Retention and deletion.

Define when invalid data is rejected, quarantined, corrected, or sent for human review.

If using specialized storage such as vector search, graph data, or time-series data, justify it and define its relationship to the primary data store.

Never claim that real data is available unless access has been confirmed.

---

# PHASE 11: SECURITY, PRIVACY, AND RESPONSIBLE DESIGN

## 31. Security architecture

Cover:

- Authentication.
- Authorization.
- Role-based or attribute-based access control.
- Least privilege.
- Session security.
- Tenant isolation where applicable.
- Input validation.
- Injection prevention.
- Encryption in transit and at rest.
- Secret storage and rotation.
- Secure file handling.
- API rate limiting.
- Dependency scanning.
- Audit logging.
- Data minimization.
- Backup security.
- Incident response.

Create a threat model with scenarios, likelihood, impact, mitigations, and verification methods.

## 32. Responsible design

Address relevant concerns involving:

- Privacy.
- Accessibility.
- Bias.
- Fairness.
- Explainability.
- User consent.
- Human oversight.
- Misuse prevention.
- Failure transparency.
- AI-specific risks.

Distinguish the controls required for the hackathon MVP from the additional controls required before production.

Do not claim regulatory compliance or certification without evidence.

---

# PHASE 12: RELIABILITY, PERFORMANCE, AND SCALABILITY

## 33. Performance engineering

Specify realistic workload assumptions and proposed targets for:

- Request latency.
- Throughput.
- Concurrency.
- Database response time.
- Model inference latency.
- Queue processing.
- Resource utilization.

Explain:

- Query optimization.
- Indexing.
- Connection pooling.
- Caching.
- Payload limits.
- Pagination.
- Background processing.
- Load testing.
- Stress testing.

Label all targets as proposed unless explicitly specified in the PDFs or established through actual measurements.

## 34. Reliability and failure handling

Explain how the system handles:

- Database outages.
- External API failures.
- Timeouts.
- Invalid inputs.
- Duplicate requests.
- Partial processing.
- Queue backlogs.
- Model failures.
- Storage failures.
- Deployment failures.
- Data corruption.

Define:

- Health checks.
- Structured logs.
- Retries with backoff and jitter.
- Idempotency.
- Circuit breakers where justified.
- Graceful degradation.
- Backup and restoration.
- Disaster recovery.
- Recovery time objective.
- Recovery point objective.
- Proposed availability objectives.
- Incident response.

Provide explicit fallback behavior for critical dependencies.

## 35. Scalability and bottleneck analysis

Plan for:

1. Local development.
2. Hackathon demonstration.
3. Initial production.
4. Growing user base.
5. Business-scale deployment.

Identify the most likely bottleneck based on the actual workflow.

For that bottleneck, explain:

- How it will be detected.
- How it will be measured.
- The initial mitigation.
- The next scaling step.
- Associated costs and trade-offs.
- The metrics that trigger scaling.

Consider horizontal scaling, load balancing, caching, queues, database read replicas, partitioning, object storage, CDNs, multi-tenancy, and regional deployment only where justified.

Do not design for hypothetical millions of users without a workload-based reason.

---

# PHASE 13: SOFTWARE DEVELOPMENT LIFECYCLE

## 36. SDLC and engineering workflow

Define the process from requirements through maintenance:

1. Requirements analysis.
2. Problem validation.
3. Architecture.
4. UX design.
5. Repository setup.
6. Implementation.
7. Code review.
8. Automated testing.
9. Integration.
10. Staging.
11. Acceptance testing.
12. Deployment.
13. Monitoring.
14. Maintenance and iteration.

Specify:

- Git branching.
- Commit conventions.
- Pull request rules.
- Coding standards.
- Definition of Ready.
- Definition of Done.
- Environment configuration.
- Issue tracking.
- Review checklists.
- Documentation.
- Release procedures.
- Rollback procedures.

Create a responsibility matrix suitable for the actual team size. If unknown, assume a small team and explain which responsibilities can be combined.

---

# PHASE 14: CI/CD AND DEVOPS

## 37. CI/CD pipeline

Design a complete automated pipeline using a justified platform, such as GitHub Actions.

Include:

1. Pull request checks.
2. Formatting and linting.
3. Type checking.
4. Unit tests.
5. Integration tests.
6. API contract tests.
7. Dependency vulnerability scanning.
8. Secret scanning.
9. Build and artifact creation.
10. Container image creation and scanning, if applicable.
11. Artifact publishing.
12. Database migration validation.
13. Staging deployment.
14. Smoke tests.
15. End-to-end tests.
16. Production approval.
17. Production deployment.
18. Post-deployment verification.
19. Rollback or roll-forward recovery.
20. Release tagging.

Provide a Mermaid pipeline diagram and a representative configuration outline appropriate to the chosen stack.

Explain:

- Development, testing, staging, and production environments.
- Secrets management.
- Artifact versioning.
- Deployment permissions.
- Database migration safety.
- Quality gates.
- Failure handling.

Never invent credentials or claim that a pipeline has been executed if it has not.

## 38. Testing strategy

Cover:

- Unit testing.
- Integration testing.
- API testing.
- Contract testing.
- Database testing.
- End-to-end testing.
- Regression testing.
- Performance testing.
- Security testing.
- Accessibility testing.
- Resilience testing.
- Backup restoration testing.
- User acceptance testing.

For each mandatory feature, provide representative test cases containing:

- Test ID.
- Related requirement.
- Preconditions.
- Input.
- Expected output.
- Edge or failure condition.
- Test level.
- Acceptance criteria.

Define release gates based on actual product correctness and risk, not arbitrary code coverage targets.

---

# PHASE 15: IMPACT AND EVIDENCE

## 39. Measurable outcomes

Identify the most meaningful metrics for the actual problem.

Possible metrics include:

- Time to complete a task.
- Cost per transaction.
- Error rate.
- Success rate.
- Manual effort.
- Throughput.
- Data accuracy.
- Time to resolve an issue.
- Accessibility.
- User satisfaction.
- Resource utilization.

For each metric, specify:

- Definition.
- Relevance.
- Baseline.
- Measurement procedure.
- Proposed target.
- Test conditions.
- Data collection.
- Known limitations.

If the baseline is unknown, define how it will be measured.

Do not invent performance improvements, accuracy rates, cost reductions, or user satisfaction results.

## 40. Before-and-after comparison

Design a fair comparison between the existing process and the proposed solution.

Define:

1. Representative task.
2. Baseline workflow.
3. Proposed workflow.
4. Equivalent test conditions.
5. Dataset and sample assumptions.
6. Timing measurement.
7. Correctness measurement.
8. Error tracking.
9. Result presentation.
10. Limitations and threats to validity.

Separate measured results from anticipated benefits.

For simulated data, explicitly identify the evaluation as simulated.

## 41. Claim-to-evidence matrix

Create a table:

| Claim | Current evidence | Verification method | Metric | Status | Limitation |
|---|---|---|---|---|---|

Evidence status must distinguish:

- Source-verified.
- Externally supported.
- Implemented and tested.
- Experimentally measured.
- User-validated.
- Simulated.
- Assumed.
- Not yet validated.

Every significant claim must have supporting evidence or a clear plan to obtain it.

---

# PHASE 16: LIVE DEMONSTRATION

## 42. Demo strategy

Design a concise, repeatable demonstration that shows:

1. The sponsor's problem.
2. The existing limitation.
3. The complete working solution.
4. The core differentiating feature.
5. The actual processing mechanism.
6. The result.
7. The measurable benefit.
8. A meaningful edge case or recovery scenario, if feasible.
9. Honest limitations and next steps.

Create a timed script containing:

- Step.
- Presenter action.
- What judges see.
- Requirement demonstrated.
- Technical mechanism.
- Supporting evidence.
- Expected result.
- Failure fallback.

Prefer one complete working workflow over numerous disconnected screens.

## 43. Demo reliability

Define:

- Demo environment.
- Seed data.
- Dataset provenance.
- Reset procedure.
- Expected outputs.
- Network dependency handling.
- Test accounts and permissions.
- Failure recovery.
- Backup demonstration.

If a component is mocked, simulated, prerecorded, or manually triggered, identify it clearly.

Do not misrepresent simulated outputs as live computation.

---

# PHASE 17: OFFICIAL JUDGING RUBRIC

## 44. Optimize for all five judging categories

The judging rubric assigns equal weight to five categories:

| Category | Weight |
|---|---:|
| Problem significance | 20% |
| Innovation | 20% |
| Technical depth | 20% |
| Feasibility | 20% |
| Demonstrable impact | 20% |
| Total | 100% |

Address each category independently.

### 44.1 Problem significance: 20%

Demonstrate:

- A specific, meaningful problem.
- Identifiable target users.
- Credible evidence.
- Clear consequences.
- Sponsor relevance.
- A practical validation plan.

### 44.2 Innovation: 20%

Demonstrate:

- Existing alternatives.
- Evidence-supported competitive gaps.
- A distinctive mechanism.
- A clear reason the solution is better for its intended users.
- A working implementation or honestly labeled prototype.
- A measurable evaluation of the improvement.

Using AI or a modern framework alone does not establish innovation.

### 44.3 Technical depth: 20%

Demonstrate:

- A justified architecture.
- Correct data modeling.
- Nontrivial technical implementation where appropriate.
- Algorithm and integration reasoning.
- API contracts.
- Security.
- Reliability.
- Automated testing.
- Performance considerations.
- A defensible engineering trade-off.

### 44.4 Feasibility: 20%

Demonstrate:

- A realistic scope.
- Risk-first validation.
- A functioning end-to-end MVP.
- Dependency-aware task planning.
- Clear distinction between current and future capabilities.
- Testing and integration time.
- Fallback strategies.
- A credible production path.

### 44.5 Demonstrable impact: 20%

Demonstrate:

- A working user journey.
- A baseline.
- A fair before-and-after comparison.
- Relevant measurements.
- Reproducible test conditions.
- Honest limitations.

## 45. Judging evidence matrix

Create a table connecting each category to:

- The relevant features.
- Required implementation.
- Evidence.
- Test results needed.
- Demo steps.
- Potential weaknesses.
- Remediation actions.
- Current readiness.

Do not assign unsupported numerical scores.

Distinguish readiness of the written plan from readiness of the actual implemented product.

---

# PHASE 18: BUSINESS ADOPTION AND PRODUCTION SCALING

## 46. Make sponsor adoption believable

Explain how the sponsor could actually adopt the solution.

Cover:

- Integration with existing systems.
- Required API and data access.
- Deployment environment.
- Authentication and permissions.
- Workflow changes.
- Employee or user onboarding.
- Training.
- Security review.
- Data governance.
- Operational ownership.
- Infrastructure.
- Cost drivers.
- Support requirements.
- Rollback and migration.
- Pilot evaluation.

Identify what the sponsor would need to provide, approve, configure, or change.

Do not assume access to proprietary systems without evidence.

## 47. Adoption roadmap

Define five stages:

**Stage A: Hackathon demonstration**

Specify what works, what is simulated, and what remains untested.

**Stage B: Sponsor validation**

Define stakeholder discussions, access approval, workflow review, and data verification.

**Stage C: Controlled pilot**

Specify users, scope, infrastructure, security, training, baseline metrics, success criteria, support, and rollback.

**Stage D: Production readiness**

Define reliability, monitoring, access control, data governance, backup, deployment, documentation, and operational requirements.

**Stage E: Wider adoption**

Define the evidence required to justify scaling, new integrations, expanded user groups, and additional investment.

## 48. Business model

Analyze, where relevant:

- Customer segments.
- Value proposition.
- Adoption barriers.
- Pricing hypotheses.
- Monetization.
- Infrastructure costs.
- Cost per user or transaction.
- Support and operations.
- Distribution.
- Partnerships.
- Retention.
- Product-market-fit validation.
- Business risks.

Clearly label hypotheses and avoid fabricated revenue projections, market sizes, or customer commitments.

## 49. Production scaling roadmap

Define:

- Hackathon MVP.
- Validated pilot.
- Initial production release.
- Scaling and operational maturity.
- Advanced product expansion.

For each stage, document features, infrastructure, security, operational changes, validation milestones, cost considerations, and exit criteria.

Explain how the system evolves without an unnecessary rewrite.

---

# PHASE 19: HACKATHON EXECUTION PLAN

## 50. Timeline and task allocation

Determine the actual deadline from the source documents or available project context.

If unavailable, explicitly assume a 48-hour hackathon and state that the schedule must be adjusted when the actual deadline is known.

Create a dependency-aware roadmap covering:

1. Source analysis.
2. Requirement inventory.
3. Problem validation.
4. Riskiest-assumption experiment.
5. Architecture and repository setup.
6. Data model and APIs.
7. End-to-end MVP.
8. Integration.
9. High-value innovation.
10. Testing and bug fixing.
11. Deployment.
12. Demo preparation.
13. Final validation.

For each task, document:

- Task ID.
- Owner.
- Duration.
- Dependencies.
- Deliverable.
- Acceptance criteria.
- Risk.
- Fallback.

Identify tasks that can run in parallel and tasks that must be completed sequentially.

Include:

- Feature freeze.
- MVP completion gate.
- Integration checkpoint.
- Testing checkpoint.
- Demo rehearsal.
- Final release readiness.

Reserve adequate time for integration and testing.

Do not assume every optional feature can be completed.

## 51. Risk register

Create a risk register containing:

- Risk ID.
- Description.
- Probability.
- Impact.
- Severity.
- Early warning indicator.
- Mitigation.
- Contingency.
- Owner.
- Related requirements.

Include technical, business, integration, data, schedule, security, adoption, cost, and demo risks.

Identify the top three risks and the actions required to address them first.

---

# PHASE 20: REQUIRED `plan.md` STRUCTURE

## 52. Generate the complete Markdown file

Create a file named exactly:

`plan.md`

Save it in the project root.

Use the following top-level sections:

1. Executive Summary
2. Source Document Analysis
3. Sponsor Objectives and Alignment
4. Problem Statement and Significance
5. Target Users and Stakeholders
6. Existing Solutions and Competitive Analysis
7. Real-World Validation Plan
8. Complete Requirements Inventory
9. Requirement Traceability Matrix
10. Proposed Solution
11. Unique Value Proposition
12. Feature Prioritization
13. Innovation and Differentiation
14. Riskiest Assumptions and Validation Experiments
15. MVP Definition and End-to-End Workflow
16. Official Judging Rubric Strategy
17. System Architecture
18. Technology Stack and Justification
19. Architecture Decision Records
20. Feature-Level Implementation Specifications
21. Algorithms and Technical Design
22. API Contracts and Integrations
23. Data Model and Database Design
24. Data Quality and Governance
25. Frontend, UX, and Accessibility
26. Security, Privacy, and Responsible Design
27. Performance and Scalability
28. Reliability and Disaster Recovery
29. SDLC and Engineering Workflow
30. CI/CD and DevOps
31. Testing and Quality Assurance
32. Measurable Impact and Evaluation
33. Claim-to-Evidence Matrix
34. Live Demo Script and Fallback
35. Hackathon Timeline and Task Allocation
36. Business Adoption and Production Roadmap
37. Business Model and Cost Considerations
38. Observability and Operations
39. Repository Structure and Developer Setup
40. Risk Register
41. Assumptions and Open Questions
42. Final Requirement Coverage Audit
43. Final Judging Readiness Assessment

Add detailed subsections, tables, Mermaid diagrams, schemas, pseudocode, examples, and checklists where they improve implementation clarity.

The file must be detailed enough to serve as the primary engineering blueprint.

Avoid generic filler, unjustified complexity, redundant explanations, and unsupported claims.

---

# PHASE 21: FINAL AUDIT AND FILE VERIFICATION

## 53. Document completeness audit

Verify:

- Both PDFs were processed page by page.
- Source filenames and page counts are recorded.
- Relevant diagrams, tables, and appendices were considered.
- All explicit requirements were extracted.
- All mandatory requirements have an implementation path.
- Sponsor alignment is documented.
- Competitive analysis supports the differentiation strategy.
- Innovation claims are justified.
- The highest-risk assumption has a validation experiment.
- The MVP contains a complete end-to-end workflow.
- APIs, algorithms, database, and architecture are consistent.
- Security, reliability, and scalability are addressed.
- CI/CD matches the chosen technology stack.
- Tests verify acceptance criteria.
- The roadmap fits the assumed deadline.
- The impact metrics are measurable.
- The demo demonstrates actual behavior.
- Sponsor adoption is realistic.
- Simulated, proposed, and implemented capabilities are clearly distinguished.

## 54. Requirement coverage report

Create a final table containing:

| Requirement ID | Requirement summary | Planned implementation | Plan section | Test or demo evidence | Status | Remaining action |
|---|---|---|---|---|---|---|

Use these statuses:

- Fully Covered.
- Partially Covered.
- Blocked.
- Not Covered.

Calculate counts for each status when the inventory allows it.

Never claim 100% coverage if mandatory requirements remain unresolved.

## 55. Judging readiness report

Create a final table:

| Category | Weight | Evidence required | Implementation or validation needed | Readiness | Remaining work |
|---|---:|---|---|---|---|
| Problem significance | 20% | Credible problem evidence | Validation and sponsor alignment | Assess honestly | Specify |
| Innovation | 20% | Verified gap and differentiation | Working differentiator and comparison | Assess honestly | Specify |
| Technical depth | 20% | Architecture, code, tests, trade-offs | Technical implementation and verification | Assess honestly | Specify |
| Feasibility | 20% | Working MVP and realistic roadmap | Integration and testing | Assess honestly | Specify |
| Demonstrable impact | 20% | Baseline and measurable benefit | Reproducible evaluation | Assess honestly | Specify |

Do not invent official score bands or claim the project is competition-ready solely because the plan is complete.

## 56. Technical consistency audit

Check that:

- Requirements map to features.
- Features map to architecture.
- APIs match workflows.
- Workflows match the database schema.
- Security controls match the data and access model.
- Algorithms have a validation strategy.
- Integrations have timeout and failure handling.
- CI/CD supports the chosen stack.
- Scaling decisions address realistic bottlenecks.
- Testing covers critical acceptance criteria.
- The roadmap respects dependencies.
- The demo matches actual planned functionality.
- All diagrams and code examples are internally consistent.

## 57. Final file creation requirements

Execute the following steps:

1. Locate both PDFs.
2. Read and analyze both documents completely.
3. Build the requirement inventory.
4. Validate the riskiest assumptions.
5. Design the sponsor-aligned solution.
6. Create the complete `plan.md`.
7. Save it directly to the project root.
8. Reopen the saved file.
9. Verify every required section is present.
10. Check diagrams, schemas, code examples, and traceability.
11. Fix missing or inconsistent content.
12. Perform the final coverage and judging audits.
13. Report any remaining blockers.

If the document is too large to create in a single operation, write it in coherent sections and verify that all sections exist in the final file.

If filesystem access is unavailable, provide the complete Markdown content and explicitly state that it could not be saved directly.

Do not stop after creating an outline, executive summary, or generic recommendations.

## 58. Final response

After completing the work, report:

- Exact path of `plan.md`.
- Names and page counts of both PDFs.
- Whether every page was processed.
- Number of requirements identified.
- Requirement coverage counts.
- The main sponsor problem and proposed solution.
- The most important innovation and its differentiation.
- The selected technology stack.
- The highest-risk assumption and validation result, if tested.
- The primary end-to-end MVP workflow.
- How the plan addresses all five judging categories.
- The impact measurement strategy.
- The sponsor adoption path.
- Unresolved assumptions and limitations.
- Whether the saved file was reopened and validated.

Never claim that implementation, testing, deployment, user research, or performance measurement occurred unless it actually did.

# FINAL DIRECTIVE

Produce an actual, detailed, internally consistent, sponsor-aligned `plan.md` file.

Every major design decision must connect to a documented requirement, a specific user problem, a verified competitive gap, a measurable outcome, or a justified engineering constraint.

Validate the riskiest assumption before committing substantial effort. Prioritize a complete working end-to-end MVP. Prove claims using evidence. Explain technical trade-offs. Make sponsor adoption credible. Optimize the proposed implementation for all five judging categories, each weighted at 20%.

**Accuracy, sponsor relevance, complete requirement coverage, meaningful innovation, technical depth, feasibility, demonstrable impact, and honest evidence take precedence over feature count and document length.**
