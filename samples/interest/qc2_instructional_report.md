# QC2 — Instructional Quality

- Lesson 2, version 2
- Score: **96.7** (rubric average × 20)
- Reviewer model: gemini:gemini-3.1-flash-lite
- Method: one LLM review call (no access to QC1) + code: quiz mapping, coverage gaps, time budget

## Summary

This lesson provides a clear, structured introduction to simple and compound interest for adult beginners. It effectively balances conceptual definitions with practical calculations and includes a variety of practice tasks and assessment questions to reinforce learning. Rubric average 4.8/5. Measured time 23.3 of 45 min. Reviewer: gemini:gemini-3.1-flash-lite.

## Outcome coverage matrix

| Outcome | Explanation | Example | Practice | Quiz |
| --- | --- | --- | --- | --- |
| Calculate simple interest for a given principal, rate, and time. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q1, Q2 |
| Calculate compound interest for a given principal, rate, and time. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q3, Q4 |
| Explain why compound interest grows faster. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q5, Q6 |

## Verb alignment (Bloom)

| Outcome | Verb | Level | Aligned | Evidence |
| --- | --- | --- | --- | --- |
| Calculate simple interest for a given principal, rate, and time. | Calculate | apply | ✓ | The lesson provides formulas and requires the learner to perform calculations in both practice tasks and quiz questions. |
| Calculate compound interest for a given principal, rate, and time. | Calculate | apply | ✓ | The lesson provides formulas and requires the learner to perform calculations in both practice tasks and quiz questions. |
| Explain why compound interest grows faster. | Explain | understand | ✓ | The practice task asks the learner to describe the phenomenon in their own words, and quiz questions test conceptual understanding. |

## Rubric (average 4.83/5)

| Criterion | Score | Justification |
| --- | --- | --- |
| clarity | 5/5 | The language is accessible, and the distinction between the two types of interest is very clear. |
| structure_flow | 5/5 | The lesson follows a logical progression from hook to concept, example, practice, and assessment. |
| jargon_before_use | 5/5 | All key terms like principal, rate, and time are defined in section 2 before being used in formulas. |
| example_quality | 4/5 | Examples are well-structured, though the inclusion of different currencies (₹ and $) might be slightly confusing for some learners. |
| practical_relevance | 5/5 | The lesson connects the math to real-world scenarios like savings accounts and loans. |
| outcome_alignment | 5/5 | The content, practice, and assessment are perfectly aligned with the stated outcomes. |

## Time budget (measured 23.3 of 45 min)

| Section | Type | Shown | Measured | Flags |
| --- | --- | --- | --- | --- |
| sec-1 The Magic of Growing Money | hook | 1 | 0.5 |  |
| sec-2 Understanding Interest Concepts, Formula | concept | 3 | 2.3 |  |
| sec-3 Worked Examples for Simple and Compound  | example | 2 | 2 |  |
| sec-4 Video Resources on Interest Mechanics | video | 5 | 5 |  |
| sec-5 Practice Exercises and Applied Explanati | activity | 8 | 8 |  |
| sec-6 Knowledge Check Instructions | knowledge_check | 5 | 5 |  |
| sec-7 Lesson Summary | summary | 1 | 0.5 |  |

## Issues

| ID | Severity | Category | Where | Text | Evidence | Suggestion | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| I-1 | minor | consistency | sec-3 | The examples use a mix of currency symbols (₹ and $). |  | Standardize all examples to a single currency or use a generic symbol to avoid unnecessary cognitive load. | open |
