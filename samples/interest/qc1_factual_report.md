# QC1 — Research & Factual Accuracy

- Lesson 2, version 1
- Score: **42.6** (% of claims supported)
- Reviewer model: gemini-3.1-flash-lite
- Method: claims extracted in code; one batched LLM verdict call; quotes verified in code

## Summary

29 of 68 claims supported (43%); 27 partial, 5 unsupported, 0 contradicted, 7 uncited. 21/23 calculations recomputed correctly. 0 contradiction(s), 0 outcome gap(s). Judge: gemini-3.1-flash-lite.

## Claim table

| Claim | Where | Cites | Verdict | Evidence quote (verified?) |
| --- | --- | --- | --- | --- |
| C1: Imagine you place 10,000 into a savings account earning a 5 percent annual return . | sec-1 | S7 | **partially_supported** | If a loan has an initial principal of $10,000 and an interest rate of 2 percent per year... Similarly, if an individual deposits $10,000 into a savings account with the same interest rate  |
| C2: Over several years, that money will grow, but the exact way it grows depends entirely on how the bank calculates your rewards . | sec-1 | S5 | **supported** | The difference between simple and compound interest is that simple interest is calculated using only the original amount whereas compound interest works out the interest on a previous amount as well. (✓ found) |
| C3: Some accounts add earnings only on your original starting amount, while others reward you on your starting amount plus every dollar of earnings you have accumulated along the way , | sec-1 | S5, S7 | **supported** | Simple interest is calculated on the original (principal) amount, whereas compound interest is calculated on the original amount and on the interest already accumulated on it. (✓ found) |
| C4: Understanding this distinction is one of the most powerful tools in personal finance , helping you decide how to manage long-term savings and evaluate the true cost of borrowing mo | sec-1 | S7, S4 | **partially_supported** | Understanding this distinction is one of the most powerful tools in personal finance, helping you decide how to manage long-term savings and evaluate the true cost of borrowing money.  |
| C5: The principal is the original amount of money deposited into an account or borrowed on a loan . | sec-2 | S3 | **supported** | The amount of money that is initially invested or borrowed is called the principal. (✓ found) |
| C6: The interest rate is the percentage used to determine how fast the balance grows over a set period, usually expressed annually and converted into a decimal form for calculations . | sec-2 | S3 | **partially_supported** | The speed at which the interest grows is called the rate. All rates are expressed as percentages.  |
| C7: Time refers to the duration the money is invested or borrowed, typically expressed in years . | sec-2 | S3 | **partially_supported** | How long money is being invested or borrowed is called time. The amount of time is measured in one year  |
| C8: Simple and compound interest represent two distinct ways to calculate these earnings . | sec-2 | S5 | **supported** | Simple interest is calculated on the original (principal) amount, whereas compound interest is calculated on the original amount and on the interest already accumulated on it. (✓ found) |
| C9: Simple interest is calculated solely on the original principal amount . | sec-2 | S5 | **supported** | Simple interest is calculated using only the original amount (✓ found) |
| C10: Because you always earn rewards on the exact same starting balance, simple interest grows linearly, creating steady and predictable increases over time . | sec-2 | S4 | **supported** | Simple interest is calculated only on the original principal, which leads to steady, predictable growth or borrowing costs over time. (✓ found) |
| C11: The formula for the final value or total amount including simple interest is expressed as A = P(1 + rt), where P is the principal, r is the annual interest rate as a decimal, and t | sec-2 | S5, S3 | **supported** | Here we use the formula A=P (1+rt) (✓ found) |
| C12: Alternatively, the total interest earned alone can be calculated as I = Prt . | sec-2 | S3 | **supported** | the formula for simple interest is {eq}I=PRT. {/eq} (✓ found) |
| C13: Compound interest is calculated on both the original principal and the accumulated interest from previous periods . | sec-2 | S4 | **supported** | Compound interest refers to a process where interest is calculated not only on the original principal but also on the accumulated interest from previous periods. (✓ found) |
| C14: This creates a snowball effect often described as earning "interest on interest," where each compounding period adds interest to a growing balance , . | sec-2 | S4, S7 | **supported** | This results in a snowball effect, where the total amount grows at an increasing rate over time. (✓ found) |
| C15: As a result, compound interest grows faster and produces exponential growth over time compared to the linear growth of simple interest . | sec-2 | S4 | **partially_supported** | Simple interest grows linearly, while compound interest benefits from “interest on interest.” This makes compound interest more powerful for long-term investing  |
| C16: The formula for compound interest to find the final accumulated amount A is A = P(1 + r)^t, where P is the principal, r is the annual interest rate as a decimal, and t is the time  | sec-2 | S8 | **unsupported** |   |
| C17: With simple interest, your earnings remain constant in each period because the base amount never changes . | sec-2 | S8 | **supported** | With simple interest, your earnings remain constant regardless of how long you save. (✓ found) |
| C18: For example, if you deposit 10,000 at a 5 percent simple interest rate, your earnings are locked at 500 every single year . | sec-2 | S8 | **unsupported** |   |
| C19: With compound interest, each year's interest is added directly to the principal balance for the next period . | sec-2 | S7 | **supported** | Compound interest is the interest on an investment or loan that is added to the principal amount, allowing for additional interest to accrue on this new total. (✓ found) |
| C20: This accumulation accelerates your growth exponentially over long time horizons, making compound interest vastly superior for long-term investments and retirement savings , . | sec-2 | S4, S8 | **supported** | Compound interest drives wealth creation by reinvesting earnings, allowing investors to create exponential growth over the long run. (✓ found) |
| C21: Failing to convert percentages to decimals: Always divide your percentage rate by 100 before plugging it into formulas (for example, 5% becomes 0.05) . | sec-2 | S3 | **partially_supported** | It's customary for financial institutions to quote a quantity called the interest rate as a percentage. ... r is the annual interest rate in decimal form  |
| C22: Confusing time periods: If a problem specifies months instead of years, you must convert the time into a fraction of a year by dividing the number of months by 12 . | sec-2 | S3 | **supported** | We use 6 divided by 12 because that indicated half a year, which is equivalent to 6 months. (✓ found) |
| C23: Applying compound formulas to simple interest scenarios: Remember that simple interest ignores accumulated past interest, whereas compound interest depends entirely on it . | sec-2 | S5 | **supported** | Simple interest is calculated using only the original amount whereas compound interest works out the interest on a previous amount as well. (✓ found) |
| C24: Here, P = 1500, r = 5% = 0.05, and t = 4 . | sec-3 | S5 | **partially_supported** | £1500 is invested for 4 years at 5% per year simple interest.  |
| C25: Step 2: Substitute the values into the formula: A = 1500 × (1 + (0.05 × 4)) . | sec-3 | S5 | **partially_supported** | Substituting these values into the simple interest formula A = P (1 + rt), we get: A = 1500 × (1 + (0.05 × 4))  |
| C26: Step 1: Identify variables: P = 10000, r = 2% = 0.02, t = 1 . | sec-3 | S7 | **partially_supported** | If a loan has an initial principal of $10,000 and an interest rate of 2 percent per year... by the end of the year he or she will owe $10,200  |
| C27: Step 2: Use the simple interest formula for interest earned I = Prt: I = 10000 × 0.02 × 1 = 200 . | sec-3 | S7 | **supported** | he or she will end the year having gained $200. (✓ found) |
| C28: Step 3: Add interest to principal to find total value A: 10000 + 200 = 10,200 . | sec-3 | S7 | **supported** | by the end of the year he or she will owe $10,200 (✓ found) |
| C29: Here, P = 8500, r = 0.3% = 0.003, and t = 5 . | sec-3 | S5 | **partially_supported** | £8500 is invested for 5 years into a bank account at 0.3% per year compound interest.  |
| C30: Step 2: Substitute into the formula: A = 8500 × (1 + 0.003)^5 . | sec-3 | S5 | **partially_supported** | A = 8500 × (1 + 0.003)^5  |
| C31: Step 1: Identify variables: P = 10000, r = 5% = 0.05, t = 3 . | sec-3 | S15 | **unsupported** |   |
| C32: Step 2: Substitute into the compound interest formula: A = 10000 × (1 + 0.05)^3 . | sec-3 | S8 | **partially_supported** | Let's use the same example: $10,000 invested at 5% for 3 years. But this time, the interest compounds annually: A = 10,000(1 + 0.05)^3  |
| C33: Step 3: Evaluate the expression: (1.05)^3 = 1.157625 . | sec-3 | S8 | **partially_supported** | (1.05)^3 = 1.157625  |
| C34: Step 4: Multiply by principal: A = 10000 × 1.157625 = 11,576.25 . | sec-3 | S8 | **partially_supported** | A = 10,000 × 1.157625 = 11,576.25  |
| C35: Final Answer: 11,576.25 (yielding 1,576.25 in total interest compared to 1,500 under simple interest) , . | sec-3 | S8, S15 | **partially_supported** | A $10,000 deposit at 5 percent simple interest over three years yields $1,500 in total interest. The same deposit at 5 percent compound interest annually yields $1,576.25 over three years.  |
| C36: To reinforce your understanding of how simple and compound interest operate and why compounding accelerates financial growth, watch the following recommended videos , . | sec-4 | S15, S17 | **supported** | What is compound interest? Compound interest is often called one of the most powerful concepts in finance. Find out what it is and how it can work for you. (✓ found) |
| C37: (Investopedia): Watch how a 10,000 deposit compares across simple and compound structures over a 3-year period . | sec-4 | S15 | **partially_supported** | A $10,000 deposit at 5 percent simple interest over three years yields $1,500 in total interest. The same deposit at 5 percent compound interest annually yields $1,576.25 over three years.  |
| C38: Difference between Simple Interest and Compound Interest: Review the core definitions, formulas, and visual distinctions between linear and exponential accumulation . | sec-4 | S17 | **supported** | This video is about the basic difference between Simple Interest and Compound Interest. (✓ found) |
| C39: Convert rate: 4% = 0.04 . | sec-5 | S3 | **supported** | All rates are expressed as percentages. (✓ found) |
| C40: Use simple interest formula I = Prt: I = 4500 × 0.04 × 2 = 360 . | sec-5 | S3 | **partially_supported** | I = Prt  |
| C41: Convert time to years: 6 months ÷ 12 = 0.5 years . | sec-5 | S3 | **supported** | We use 6 divided by 12 because that indicated half a year (✓ found) |
| C42: Convert rate: 6% = 0.06 . | sec-5 | S3 | **supported** | All rates are expressed as percentages. (✓ found) |
| C43: Calculate interest: I = 2000 × 0.06 × 0.5 = 60 . | sec-5 | S3 | **partially_supported** | I = Prt  |
| C44: Identify variables: P = 5000, r = 0.04, t = 2 . | sec-5 | S8 | **unsupported** |   |
| C45: Use formula A = P(1 + r)^t: A = 5000 × (1 + 0.04)^2 . | sec-5 | S8 | **partially_supported** | A = P(1 + r)^t  |
| C46: Calculate: (1.04)^2 = 1.0816 . | sec-5 | S8 | **partially_supported** | (1.04)^2 = 1.0816  |
| C47: Identify variables: P = 2000, r = 0.05, t = 3 . | sec-5 | S8 | **unsupported** |   |
| C48: Formula: A = 2000 × (1 + 0.05)^3 . | sec-5 | S8 | **partially_supported** | A = P(1 + r)^t  |
| C49: Calculate: (1.05)^3 = 1.157625 . | sec-5 | S8 | **partially_supported** | (1.05)^3 = 1.157625  |
| C50: Model Answer: Compound interest grows faster because it calculates earnings on both the original principal and all previously accumulated interest from past periods , . | sec-5 | S4, S8 | **supported** | Compound interest refers to a process where interest is calculated not only on the original principal but also on the accumulated interest from previous periods. (✓ found) |
| C51: This creates a "snowball effect" or "interest on interest," whereas simple interest calculates earnings solely on the original starting principal every year, resulting in flat, lin | sec-5 | S4, S8 | **supported** | Simple interest is calculated solely on the original principal amount, resulting in fixed, predictable growth. (✓ found) |
| C52: Principal and Rates: The principal is your starting amount, and interest rates determine how fast your balance grows when converted to a decimal . | sec-7 | S3 | **partially_supported** | The amount of money that is initially invested or borrowed is called the principal. The speed at which the interest grows is called the rate.  |
| C53: Simple Interest Mechanics: Simple interest is calculated strictly on the original principal amount using A = P(1 + rt), producing steady, linear growth over time , . | sec-7 | S4, S5 | **supported** | Simple interest is calculated only on the original principal, which leads to steady, predictable growth (✓ found) |
| C54: Compound Interest Mechanics: Compound interest is calculated on both the original principal and accumulated past interest using A = P(1 + r)^t , . | sec-7 | S4, S8 | **supported** | Compound interest refers to a process where interest is calculated not only on the original principal but also on the accumulated interest from previous periods. (✓ found) |
| C55: The Power of Compounding: Compound interest generates exponential growth and higher returns over long periods due to earning "interest on interest" , . | sec-7 | S4, S8 | **supported** | Compound interest drives wealth creation by reinvesting earnings, allowing investors to create exponential growth over the long run. (✓ found) |
| C56: Answer to 'You invest 2,000 at an annual simple interest rate of 5% for 3 years. What is the total simple interest earned?': 300. Using the simple interest formula I = Prt, multipl | quiz-Q1 | S3 | **partially_supported** | Using the simple interest formula I = Prt, multiply 2,000 by 0.05 and 3 years, which equals 300  |
| C57: Answer to 'If you borrow 5,000 at a simple interest rate of 4% per year for 6 months, how much interest do you pay?': 100. Time must be expressed in years, so 6 months is 0.5 years | quiz-Q2 | S3 | **partially_supported** | Time must be expressed in years, so 6 months is 0.5 years. Multiplying 5,000 × 0.04 × 0.5 gives 100  |
| C58: Answer to 'You deposit 10,000 into an account earning 5 percent compound interest annually. What is the total accumulated amount after 3 years?': 11,576.25. Using the compound inte | quiz-Q3 | S8, S15 | **partially_supported** | Using the compound interest formula A = P(1 + r)^t, 10,000 × (1.05)^3 results in 11,576.25  |
| C59: Answer to 'An investment of £8,500 is placed into an account at 0.3% per year compound interest for 5 years. What is the final value?': £8,628.79. Using A = P(1 + r)^t with P = 850 | quiz-Q4 | S5 | **partially_supported** | Using A = P(1 + r)^t with P = 8500, r = 0.003, and t = 5 yields approximately £8,628.79  |
| C60: Answer to 'Why does compound interest grow faster than simple interest over extended time periods?': Compound interest earns interest on both the original principal and accumulated | quiz-Q5 | S4, S7 | **supported** | Compound interest refers to a process where interest is calculated not only on the original principal but also on the accumulated interest from previous periods. (✓ found) |
| C61: Answer to 'What is the primary structural difference in the growth pattern between simple and compound interest over time?': Simple interest grows linearly with steady increases, w | quiz-Q6 | S4 | **supported** | Simple interest grows linearly, while compound interest benefits from “interest on interest.” (✓ found) |
| U1: Before calculating financial growth, we must define the core terms. | sec-2 |  | **uncited** |   |
| U2: To understand why compound interest grows faster, consider the mechanics of accumulation. | sec-2 |  | **uncited** |   |
| U3: Problem: £1,500 is invested for 4 years at 5% per year simple interest. | sec-3 |  | **uncited** |   |
| U4: Problem: 10,000 is invested in a simple interest account with a 2 percent annual rate for 1 year. | sec-3 |  | **uncited** |   |
| U5: Problem: £8,500 is invested for 5 years into a bank account at 0.3% per year compound interest. | sec-3 |  | **uncited** |   |
| U6: Problem: 10,000 is deposited into an account earning 5 percent compound interest annually for 3 years. | sec-3 |  | **uncited** |   |
| U7: Here are the key takeaways from this lesson: | sec-7 |  | **uncited** |   |

## Numeric checks (recomputed in Python)

- ✓ `(5/100) = 0.05` (sec-3) — matches
- ✓ `0.05 * 4 = 0.20` (sec-3) — matches
- ✓ `1 + 0.20 = 1.20` (sec-3) — matches
- ✓ `1500 * 1.20 = 1800` (sec-3) — matches
- ✓ `(2/100) = 0.02` (sec-3) — matches
- ✓ `10000 * 0.02 * 1 = 200` (sec-3) — matches
- ✓ `10000 + 200 = 10200` (sec-3) — matches
- ✓ `(0.3/100) = 0.003` (sec-3) — matches
- ✓ `1 + 0.003 = 1.003` (sec-3) — matches
- ✗ `(1.003)**5 ≈ 1.50896` (sec-3) — (1.003)**5 = 1.01509, but the text says 1.50896
- ✗ `8500 * 1.008985   = 8628.79` (sec-3) — 8500 * 1.008985 = 8,576.37, but the text says 8628.79
- ✓ `(5/100) = 0.05` (sec-3) — matches
- ✓ `(1.05)**3 = 1.157625` (sec-3) — matches
- ✓ `10000 * 1.157625 = 11576.25` (sec-3) — matches
- ✓ `(4/100) = 0.04` (sec-5) — matches
- ✓ `4500 * 0.04 * 2 = 360` (sec-5) — matches
- ✓ `4500 + 360 = 4860` (sec-5) — matches
- ✓ `(6/100) = 0.06` (sec-5) — matches
- ✓ `2000 * 0.06 * 0.5 = 60` (sec-5) — matches
- ✓ `(1.04)**2 = 1.0816` (sec-5) — matches
- ✓ `5000 * 1.0816 = 5408` (sec-5) — matches
- ✓ `(1.05)**3 = 1.157625` (sec-5) — matches
- ✓ `2000 * 1.157625 = 2315.25` (sec-5) — matches

## Source audit

- Most-cited source S8 carries 19 of 61 cited claims (31%).

## Outcome evidence gaps

_None._

## Issues

| ID | Severity | Category | Where | Text | Evidence | Suggestion | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | critical | arithmetic_error | sec-3 | (1.003)**5 ≈ 1.50896 | (1.003)**5 = 1.01509, but the text says 1.50896 | Recompute this step; the numbers in the text do not match. | open |
| F-2 | critical | arithmetic_error | sec-3 | 8500 * 1.008985   = 8628.79 | 8500 * 1.008985 = 8,576.37, but the text says 8628.79 | Recompute this step; the numbers in the text do not match. | open |
| F-3 | major | claim_unsupported | sec-2 | The formula for compound interest to find the final accumulated amount A is A = P(1 + r)^t, where P is the principal, r is the annual interest rate as a decimal, and t is the time in years . | The provided source S8 does not explicitly state the formula A = P(1 + r)^t in the excerpt. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-4 | major | claim_unsupported | sec-2 | For example, if you deposit 10,000 at a 5 percent simple interest rate, your earnings are locked at 500 every single year . | The source S8 mentions a 10,000 deposit at 5% for 3 years but does not explicitly state the earnings are locked at 500 every single year. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-5 | major | claim_unsupported | sec-3 | Step 1: Identify variables: P = 10000, r = 5% = 0.05, t = 3 . | Source S15 does not contain the specific variable identification step for these values. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-6 | major | claim_unsupported | sec-5 | Identify variables: P = 5000, r = 0.04, t = 2 . | Source S8 does not contain this specific variable identification. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-7 | major | claim_unsupported | sec-5 | Identify variables: P = 2000, r = 0.05, t = 3 . | Source S8 does not contain this specific variable identification. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-8 | major | uncited_claim | sec-2 | Before calculating financial growth, we must define the core terms. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-9 | major | uncited_claim | sec-2 | To understand why compound interest grows faster, consider the mechanics of accumulation. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-10 | major | uncited_claim | sec-3 | Problem: £1,500 is invested for 4 years at 5% per year simple interest. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-11 | major | uncited_claim | sec-3 | Problem: 10,000 is invested in a simple interest account with a 2 percent annual rate for 1 year. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-12 | major | uncited_claim | sec-3 | Problem: £8,500 is invested for 5 years into a bank account at 0.3% per year compound interest. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-13 | major | uncited_claim | sec-3 | Problem: 10,000 is deposited into an account earning 5 percent compound interest annually for 3 years. |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
| F-14 | minor | claim_partially_supported | sec-1 | Imagine you place 10,000 into a savings account earning a 5 percent annual return . | If a loan has an initial principal of $10,000 and an interest rate of 2 percent per year... Similarly, if an individual deposits $10,000 into a savings account with the same interest rate | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-15 | minor | claim_partially_supported | sec-1 | Understanding this distinction is one of the most powerful tools in personal finance , helping you decide how to manage long-term savings and evaluate the true cost of borrowing money . | Understanding this distinction is one of the most powerful tools in personal finance, helping you decide how to manage long-term savings and evaluate the true cost of borrowing money. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-16 | minor | claim_partially_supported | sec-2 | The interest rate is the percentage used to determine how fast the balance grows over a set period, usually expressed annually and converted into a decimal form for calculations . | The speed at which the interest grows is called the rate. All rates are expressed as percentages. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-17 | minor | claim_partially_supported | sec-2 | Time refers to the duration the money is invested or borrowed, typically expressed in years . | How long money is being invested or borrowed is called time. The amount of time is measured in one year | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-18 | minor | claim_partially_supported | sec-2 | As a result, compound interest grows faster and produces exponential growth over time compared to the linear growth of simple interest . | Simple interest grows linearly, while compound interest benefits from “interest on interest.” This makes compound interest more powerful for long-term investing | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-19 | minor | claim_partially_supported | sec-2 | Failing to convert percentages to decimals: Always divide your percentage rate by 100 before plugging it into formulas (for example, 5% becomes 0.05) . | It's customary for financial institutions to quote a quantity called the interest rate as a percentage. ... r is the annual interest rate in decimal form | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-20 | minor | claim_partially_supported | sec-3 | Here, P = 1500, r = 5% = 0.05, and t = 4 . | £1500 is invested for 4 years at 5% per year simple interest. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-21 | minor | claim_partially_supported | sec-3 | Step 2: Substitute the values into the formula: A = 1500 × (1 + (0.05 × 4)) . | Substituting these values into the simple interest formula A = P (1 + rt), we get: A = 1500 × (1 + (0.05 × 4)) | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-22 | minor | claim_partially_supported | sec-3 | Step 1: Identify variables: P = 10000, r = 2% = 0.02, t = 1 . | If a loan has an initial principal of $10,000 and an interest rate of 2 percent per year... by the end of the year he or she will owe $10,200 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-23 | minor | claim_partially_supported | sec-3 | Here, P = 8500, r = 0.3% = 0.003, and t = 5 . | £8500 is invested for 5 years into a bank account at 0.3% per year compound interest. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-24 | minor | claim_partially_supported | sec-3 | Step 2: Substitute into the formula: A = 8500 × (1 + 0.003)^5 . | A = 8500 × (1 + 0.003)^5 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-25 | minor | claim_partially_supported | sec-3 | Step 2: Substitute into the compound interest formula: A = 10000 × (1 + 0.05)^3 . | Let's use the same example: $10,000 invested at 5% for 3 years. But this time, the interest compounds annually: A = 10,000(1 + 0.05)^3 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-26 | minor | claim_partially_supported | sec-3 | Step 3: Evaluate the expression: (1.05)^3 = 1.157625 . | (1.05)^3 = 1.157625 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-27 | minor | claim_partially_supported | sec-3 | Step 4: Multiply by principal: A = 10000 × 1.157625 = 11,576.25 . | A = 10,000 × 1.157625 = 11,576.25 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-28 | minor | claim_partially_supported | sec-3 | Final Answer: 11,576.25 (yielding 1,576.25 in total interest compared to 1,500 under simple interest) , . | A $10,000 deposit at 5 percent simple interest over three years yields $1,500 in total interest. The same deposit at 5 percent compound interest annually yields $1,576.25 over three years. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-29 | minor | claim_partially_supported | sec-4 | (Investopedia): Watch how a 10,000 deposit compares across simple and compound structures over a 3-year period . | A $10,000 deposit at 5 percent simple interest over three years yields $1,500 in total interest. The same deposit at 5 percent compound interest annually yields $1,576.25 over three years. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-30 | minor | claim_partially_supported | sec-5 | Use simple interest formula I = Prt: I = 4500 × 0.04 × 2 = 360 . | I = Prt | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-31 | minor | claim_partially_supported | sec-5 | Calculate interest: I = 2000 × 0.06 × 0.5 = 60 . | I = Prt | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-32 | minor | claim_partially_supported | sec-5 | Use formula A = P(1 + r)^t: A = 5000 × (1 + 0.04)^2 . | A = P(1 + r)^t | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-33 | minor | claim_partially_supported | sec-5 | Calculate: (1.04)^2 = 1.0816 . | (1.04)^2 = 1.0816 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-34 | minor | claim_partially_supported | sec-5 | Formula: A = 2000 × (1 + 0.05)^3 . | A = P(1 + r)^t | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-35 | minor | claim_partially_supported | sec-5 | Calculate: (1.05)^3 = 1.157625 . | (1.05)^3 = 1.157625 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-36 | minor | claim_partially_supported | sec-7 | Principal and Rates: The principal is your starting amount, and interest rates determine how fast your balance grows when converted to a decimal . | The amount of money that is initially invested or borrowed is called the principal. The speed at which the interest grows is called the rate. | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-37 | minor | claim_partially_supported | quiz-Q1 | Answer to 'You invest 2,000 at an annual simple interest rate of 5% for 3 years. What is the total simple interest earned?': 300. Using the simple interest formula I = Prt, multiply 2,000 by 0.05 and 3 years, which equals 300 . | Using the simple interest formula I = Prt, multiply 2,000 by 0.05 and 3 years, which equals 300 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-38 | minor | claim_partially_supported | quiz-Q2 | Answer to 'If you borrow 5,000 at a simple interest rate of 4% per year for 6 months, how much interest do you pay?': 100. Time must be expressed in years, so 6 months is 0.5 years. Multiplying 5,000 × 0.04 × 0.5 gives 100 . | Time must be expressed in years, so 6 months is 0.5 years. Multiplying 5,000 × 0.04 × 0.5 gives 100 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-39 | minor | claim_partially_supported | quiz-Q3 | Answer to 'You deposit 10,000 into an account earning 5 percent compound interest annually. What is the total accumulated amount after 3 years?': 11,576.25. Using the compound interest formula A = P(1 + r)^t, 10,000 × (1.05)^3 results in 11,576.25 , . | Using the compound interest formula A = P(1 + r)^t, 10,000 × (1.05)^3 results in 11,576.25 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-40 | minor | claim_partially_supported | quiz-Q4 | Answer to 'An investment of £8,500 is placed into an account at 0.3% per year compound interest for 5 years. What is the final value?': £8,628.79. Using A = P(1 + r)^t with P = 8500, r = 0.003, and t = 5 yields approximately £8,628.79 . | Using A = P(1 + r)^t with P = 8500, r = 0.003, and t = 5 yields approximately £8,628.79 | Rewrite the claim so it says only what the cited source states, cite a source that supports it, or remove it. | open |
| F-41 | minor | uncited_claim | sec-7 | Here are the key takeaways from this lesson: |  | Add a citation to a source that states this, or remove/soften the sentence. | open |
