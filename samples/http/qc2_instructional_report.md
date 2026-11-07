# QC2 — Instructional Quality

- Lesson 1, version 1
- Score: **96.7** (rubric average × 20)
- Reviewer model: gemini-3.5-flash-lite
- Method: one LLM review call (no access to QC1) + code: quiz mapping, coverage gaps, time budget

## Summary

This self-paced lesson covers HTTP GET and POST methods as well as 2xx, 4xx, and 5xx response status categories. It features clear concept explanations, worked examples, practice scenarios, external video links, and multiple-choice questions. Rubric average 4.8/5. Measured time 28.8 of 45 min. Reviewer: gemini-3.5-flash-lite.

## Outcome coverage matrix

| Outcome | Explanation | Example | Practice | Quiz |
| --- | --- | --- | --- | --- |
| Explain the HTTP GET method | ✓ sec-1, sec-2, sec-5 | ✓ sec-5 | ✓ sec-6 | ✓ Q1, Q2 |
| Explain the HTTP POST method | ✓ sec-3, sec-5 | ✓ sec-5 | ✓ sec-6 | ✓ Q3, Q4 |
| Distinguish between 2xx, 4xx, and 5xx response status categories | ✓ sec-4, sec-5 | ✓ sec-5 | ✓ sec-6 | ✓ Q5, Q6 |

## Verb alignment (Bloom)

| Outcome | Verb | Level | Aligned | Evidence |
| --- | --- | --- | --- | --- |
| Explain the HTTP GET method | Explain | understand | ✓ | The practice activity and quiz items require identifying and describing GET method characteristics and purposes. |
| Explain the HTTP POST method | Explain | understand | ✓ | The practice activity and quiz items require identifying and describing POST method behaviors and state changes. |
| Distinguish between 2xx, 4xx, and 5xx response status categories | Distinguish | analyze | ✓ | The practice activity requires learners to analyze distinct scenarios and choose between 2xx, 4xx, and 5xx categories, matching the outcome. |

## Rubric (average 4.83/5)

| Criterion | Score | Justification |
| --- | --- | --- |
| clarity | 5/5 | The language is precise, highly accessible to adult beginners, and avoids unnecessary complexity. |
| structure_flow | 5/5 | Logical progression from basic definitions to methods, status codes, examples, and practice. |
| jargon_before_use | 4/5 | Most terms like idempotent and safe are defined well, though brief introductory glosses could be sharper. |
| example_quality | 5/5 | Real-world scenarios like weather fetching and sign-up forms make abstract concepts concrete. |
| practical_relevance | 5/5 | Directly applies to web browsing, API interactions, and debugging common web errors. |
| outcome_alignment | 5/5 | Every outcome is directly supported by explanations, examples, practice tasks, and quiz questions. |

## Time budget (measured 28.8 of 45 min)

| Section | Type | Shown | Measured | Flags |
| --- | --- | --- | --- | --- |
| sec-1 Introduction: How Devices Talk on the We | hook | 1 | 0.6 |  |
| sec-2 Understanding the HTTP GET Method | concept | 2 | 1.2 |  |
| sec-3 Understanding the HTTP POST Method | concept | 2 | 1.4 |  |
| sec-4 HTTP Response Status Categories: 2xx, 4x | concept | 2 | 1.7 |  |
| sec-5 Worked Examples: Analyzing Requests and  | example | 2 | 1.7 |  |
| sec-6 Practice Activity: Scenario Classificati | activity | 5 | 5 |  |
| sec-7 Recommended Video Lessons | video | 11 | 10.5 |  |
| sec-8 Knowledge Check Instructions | knowledge_check | 6 | 6 |  |
| sec-9 Lesson Summary | summary | 1 | 0.7 |  |

## Issues

| ID | Severity | Category | Where | Text | Evidence | Suggestion | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| I-1 | minor | Interactivity | sec-6 | Blank task fields for practice | The practice activity lists method, status category, and explanation fields as blank lines without interactive input elements. | Provide immediate collapsible answer keys or explicit instructions for learners to check their work on scratch paper. | open |
