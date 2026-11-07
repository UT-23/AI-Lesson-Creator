# QC2 — Instructional Quality

- Lesson 2, version 1
- Score: **96.7** (rubric average × 20)
- Reviewer model: gemini-3.1-flash-lite
- Method: one LLM review call (no access to QC1) + code: quiz mapping, coverage gaps, time budget

## Summary

This lesson provides a clear, structured introduction to simple and compound interest for adult beginners. It effectively balances conceptual explanations with practical examples and includes a variety of practice tasks and quiz questions to reinforce learning. Rubric average 4.8/5. Measured time 23.3 of 45 min. Reviewer: gemini-3.1-flash-lite.

## Outcome coverage matrix

| Outcome | Explanation | Example | Practice | Quiz |
| --- | --- | --- | --- | --- |
| Calculate simple interest for a given principal, rate, and time. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q1, Q2 |
| Calculate compound interest for a given principal, rate, and time. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q3, Q4 |
| Explain why compound interest grows faster. | ✓ sec-2 | ✓ sec-3 | ✓ sec-5 | ✓ Q5, Q6 |

## Verb alignment (Bloom)

| Outcome | Verb | Level | Aligned | Evidence |
| --- | --- | --- | --- | --- |
| Calculate simple interest for a given principal, rate, and time. | Calculate | apply | ✓ | The learner is required to use the formula I=Prt and A=P(1+rt) in both practice tasks and quiz questions. |
| Calculate compound interest for a given principal, rate, and time. | Calculate | apply | ✓ | The learner must perform exponentiation and multiplication in practice tasks and quiz questions. |
| Explain why compound interest grows faster. | Explain | understand | ✓ | Task 5 requires the learner to synthesize the concept in their own words, and quiz questions Q5/Q6 test the underlying logic. |

## Rubric (average 4.83/5)

| Criterion | Score | Justification |
| --- | --- | --- |
| clarity | 5/5 | The language is accessible and professional, ideal for adult learners. |
| structure_flow | 5/5 | Logical progression from hook to concept to practice. |
| jargon_before_use | 5/5 | All terms like principal and compounding are defined before they are used in formulas. |
| example_quality | 4/5 | Examples are clear, though the currency switch from $ to £ in examples 1 and 3 is slightly distracting. |
| practical_relevance | 5/5 | The lesson connects math to real-world financial decisions. |
| outcome_alignment | 5/5 | All outcomes are directly supported by practice and assessment. |

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
| I-1 | minor | consistency | sec-3 | Switching between £ and $ in examples. |  | Standardize all examples to one currency to avoid unnecessary cognitive load for the learner. | open |
