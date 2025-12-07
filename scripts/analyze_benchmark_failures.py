#!/usr/bin/env python3
"""
Analyze LongMemEval benchmark failures and generate prompt improvements.

This script:
1. Parses benchmark results to find incorrect questions by category
2. Uses Groq to generate what correct answers should have been
3. Analyzes the original benchmark prompt
4. Suggests prompt improvements to fix the failure cases

Usage:
    python scripts/analyze_benchmark_failures.py --category single-session-preference
    python scripts/analyze_benchmark_failures.py --category multi-session --max-examples 5
"""

import json
import argparse
import asyncio
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import sys
from dotenv import load_dotenv
import pydantic

# Load environment variables from .env file
script_dir = Path(__file__).parent.parent
env_file = script_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Add the hindsight-api directory to Python path
sys.path.append(str(script_dir / "hindsight-api"))

from hindsight_api.engine.llm_wrapper import LLMConfig


async def make_api_call_with_retry(client, model, messages, max_tokens=1000, temperature=0.1, seed=4242, response_format=None, max_retries=3):
    """Make API call with retry logic for rate limits."""
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "seed": seed
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await client.chat.completions.create(**kwargs)
            return response
        except Exception as e:
            if "rate_limit_exceeded" in str(e) and attempt < max_retries - 1:
                # Extract wait time from error message or use exponential backoff
                if "Please try again in" in str(e):
                    import re
                    match = re.search(r'Please try again in (\d+\.?\d*)s', str(e))
                    wait_time = float(match.group(1)) if match else 2 ** attempt
                else:
                    wait_time = 2 ** attempt

                print(f"    Rate limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}...")
                await asyncio.sleep(wait_time)
            else:
                raise e
    raise Exception("Max retries exceeded")


class JudgeResponse(pydantic.BaseModel):
    """Judge response format."""
    correct: bool
    reasoning: str


@dataclass
class FailureCase:
    """Represents a single failure case from the benchmark."""
    question: str
    correct_answer: str
    predicted_answer: str
    retrieved_memories: List[Dict[str, Any]]
    chunks: Dict[str, Any]
    correctness_reasoning: str
    category: str


class BenchmarkAnalyzer:
    """Analyzes benchmark failures and generates prompt improvements."""

    def __init__(self):
        """Initialize the analyzer with Groq LLM configuration."""
        self.llm_config = LLMConfig.for_answer_generation()
        self.client = self.llm_config._client  # Use raw client to bypass LLMConfig issues

        # Initialize judge LLM config
        self.judge_config = LLMConfig.for_judge()
        self.judge_client = self.judge_config._client

    def load_benchmark_results(self, results_path: Path) -> Dict[str, Any]:
        """Load benchmark results from JSON file."""
        with open(results_path, 'r') as f:
            return json.load(f)

    def extract_failures_by_category(self, results: Dict[str, Any], category: str) -> List[FailureCase]:
        """Extract all failure cases for a specific category."""
        failures = []

        for item_result in results.get('item_results', []):
            for detail in item_result['metrics'].get('detailed_results', []):
                # Check if this is an incorrect answer in the target category
                if (detail.get('category') == category and
                    detail.get('is_correct') == False and
                    not detail.get('is_invalid', False)):

                    failure = FailureCase(
                        question=detail['question'],
                        correct_answer=detail['correct_answer'],
                        predicted_answer=detail['predicted_answer'],
                        retrieved_memories=detail.get('retrieved_memories', []),
                        chunks=detail.get('chunks', {}),
                        correctness_reasoning=detail.get('correctness_reasoning', ''),
                        category=category
                    )
                    failures.append(failure)

        return failures

    async def judge_answer(self, question: str, correct_answer: str, predicted_answer: str, category: str) -> Tuple[bool, str]:
        """Use the same judge logic as the benchmark to validate an answer."""

        # Use the exact same category-specific prompts as the benchmark
        if category in ['single-session-user', 'single-session-assistant', 'multi-session']:
            prompt_content = f"""Evaluate if the model response contains the correct answer to the question.

I will give you a question, a correct answer, and a response from a model.
Please set correct=true if the response contains the correct answer. Otherwise, set correct=no.
If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also set correct=true.
If the response only contains a subset of the information required by the answer, set correct=false

Question: {question}

Correct Answer: {correct_answer}

Model Response: {predicted_answer}

Evaluation criteria:
- Set correct=true if the response contains the correct answer
- Set correct=true if the response is equivalent to the correct answer or contains intermediate steps
- Set correct=false if the response is incorrect or missing key information

Provide your evaluation as JSON with:
- reasoning: One sentence explanation
- correct: true or false"""

        elif category == 'temporal-reasoning':
            prompt_content = f"""
I will give you a question, a correct answer, and a response from a model.
Please set correct=true if the response contains the correct answer. Otherwise, set correct=false.
If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also set correct=true.
If the response only contains a subset of the information required by the answer, answer correct=false.
In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct.

Question: {question}
Gold answer: {correct_answer}
Generated answer: {predicted_answer}
First, provide a short (one sentence) explanation of your reasoning. Short reasoning is preferred.
If it's correct, set correct=true."""

        elif category == 'knowledge-update':
            prompt_content = f"""
I will give you a question, a correct answer, and a response from a model.
Please set correct=true if the response contains the correct answer. Otherwise, set correct=false.
If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.

Question: {question}
Gold answer: {correct_answer}
Generated answer: {predicted_answer}
First, provide a short (one sentence) explanation of your reasoning. Short reasoning is preferred.
If it's correct, set correct=true."""

        elif category == 'single-session-preference':
            prompt_content = f"""
I will give you a question, a answer for desired personalized response, and a response from a model.
Please set correct=true if the response satisfies the desired response. Otherwise, set correct=false.
The model does not need to reflect all the points in the desired response. The response is correct as long as it recalls and utilizes the user's personal information correctly.

Question: {question}
Gold answer: {correct_answer}
Generated answer: {predicted_answer}
First, provide a short (one sentence) explanation of your reasoning. Short reasoning is preferred.
If it's correct, set correct=true."""

        else:
            # Default LoComo-style evaluation
            prompt_content = f"""Your task is to label an answer to a question as 'CORRECT' or 'WRONG'. You will be given the following data:
(1) a question (posed by one user to another user),
(2) a 'gold' (ground truth) answer,
(3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT.

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.
There's an edge case where the actual answer can't be found in the data and in that case the gold answer will say so (e.g. 'You did not mention this information.'); if the generated answer says that it cannot be answered or it doesn't know all the details, it should be counted as CORRECT.

Question: {question}
Gold answer: {correct_answer}
Generated answer: {predicted_answer}
First, provide a short (one sentence) explanation of your reasoning. Short reasoning is preferred.
If it's correct, set correct=true."""

        try:
            # Use retry function for judge call
            messages = [{
                "role": "user",
                "content": f"{prompt_content}\n\nRespond in JSON format with 'correct' (boolean) and 'reasoning' (string) fields."
            }]

            response = await make_api_call_with_retry(
                client=self.judge_client,
                model=self.judge_config.model,
                messages=messages,
                max_tokens=4096,
                temperature=0,
                seed=4242,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            return result.get('correct', False), result.get('reasoning', 'No reasoning provided')

        except Exception as e:
            print(f"    Judge error: {str(e)}")
            return False, f"Judge error: {str(e)}"

    async def generate_correct_answer(self, failure: FailureCase, max_attempts: int = 10) -> str:
        """Use Groq to generate what the correct answer should have been, with judge validation."""

        # Recreate the exact same recall_result structure that the benchmark uses
        recall_result = {
            "results": failure.retrieved_memories,
            "chunks": failure.chunks,
            "entities": {}  # We don't have entities in the saved results, but benchmark expects this key
        }

        # Use the exact same context formatting as the benchmark (JSON format)
        context = json.dumps(recall_result)

        for attempt in range(max_attempts):
            print(f"    Attempt {attempt + 1}/{max_attempts}...")

            # Use the exact same prompt template as the benchmark
            prompt_template = self.get_original_prompt_template()

            # Format the prompt exactly like the benchmark does
            prompt_content = prompt_template.format(
                context_instructions="",  # Empty for default benchmark
                question=failure.question,
                formatted_question_date="Not specified",  # We don't have question dates in our failure data
                context=context
            )

            try:
                # Generate candidate answer using exact benchmark prompt with retry
                response = await make_api_call_with_retry(
                    client=self.client,
                    model=self.llm_config.model,
                    messages=[{"role": "user", "content": prompt_content}],
                    max_tokens=1000,  # Allow much longer answers
                    temperature=0.1 + (attempt * 0.05),  # Increase temperature slightly with each attempt
                    seed=4242 + attempt  # Different seed for each attempt
                )

                candidate_answer = response.choices[0].message.content
                if not candidate_answer:
                    print(f"      Empty response, trying again...")
                    continue

                candidate_answer = candidate_answer.strip()
                print(f"      Generated: {candidate_answer}")

                # Validate with judge
                is_correct, judge_reasoning = await self.judge_answer(
                    failure.question,
                    failure.correct_answer,
                    candidate_answer,
                    failure.category
                )

                print(f"      Judge says: {'✓ CORRECT' if is_correct else '✗ INCORRECT'} - {judge_reasoning}")

                if is_correct:
                    return candidate_answer

            except Exception as e:
                print(f"      Error in attempt {attempt + 1}: {str(e)}")

        # If we get here, we failed all attempts
        return f"Failed to generate judge-validated answer after {max_attempts} attempts"

    def get_original_prompt_template(self) -> str:
        """Extract the original prompt template from the longmemeval benchmark code."""
        # This is the prompt template from longmemeval_benchmark.py
        return """You are a helpful assistant that must answer user questions based on the previous conversations.

{context_instructions}**Answer Guidelines:**
1. Start by scanning retrieved context to understand the facts and events that happened and the timeline.
2. Reason about all the memories and find the right answer, considering the most recent memory as an update of the current facts.
3. If you have 2 possible answers, just say both.

In general the answer must be comprehensive and plenty of details from the retrieved context.

For quantitative/counting questions ("how many..."): First list each unique item in your reasoning (1. X, 2. Y, 3. Z...), scanning ALL facts, then count them for your answer.
If questions asks a location (where...?) make sure to include the location name.
For recommendation questions ("can you recommend...", "suggest...", "any tips..."): DO NOT give actual recommendations. Instead, describe what KIND the user would prefer based on their context. Example answer format: "The user would prefer recommendations for [category] that focus on [their interest]. They would not prefer [what to avoid based on context]."
For questions asking for help or instructions, consider the users' recent memories and previous interactions with the assistant to understand their current situation better (recent purchases, specific product models used..)
For specific number/value questions, use the context to understand what is the most up-to-date number based on recency, but also include the reasoning (in the answer) on previous possible values and why you think are less relevant.
For open questions, include as much details as possible from different sources that are relevant.
For questions where a specific entity/role is mentioned and it's different from your memory, just say the truth, don't make up anything just to fulfill the question. For example, if the question is about a specific sport, you should consider if the memories and the question are about the same sport. (e.g. american football vs soccer, shows vs podcasts)
For comparative questions, say you don't know the answer if you don't have information about both sides. (or more sides)
For questions related to time/date, carefully review the question date and the memories date to correctly answer the question.
For questions related to time/date calculation (e.g. How many days passed between X and Y?), carefully review the memories date to correctly answer the question and only provide an answer if you have information about both X and Y, otherwise say it's not possible to calculate and why.

Consider assistant's previous actions (e.g., bookings, reminders) as impactful to the user experiences.

Question: {question}
Question Date: {formatted_question_date}

Retrieved Context:
{context}

Answer:"""

    async def suggest_prompt_improvements(self, failures: List[FailureCase], category: str, correct_answers: List[str]) -> str:
        """Use LLM to suggest improvements to the benchmark prompt."""

        original_prompt = self.get_original_prompt_template()

        # Create examples of failures
        failure_examples = ""
        for i, (failure, correct_answer) in enumerate(zip(failures, correct_answers), 1):
            # Create summary of both memories and chunks for brevity
            context_summary = []

            # Add memory summaries
            for j, memory in enumerate(failure.retrieved_memories[:3], 1):  # Limit to first 3 memories for brevity
                context_summary.append(f"  Memory {j}: {memory.get('text', '')[:100]}...")

            # Add chunk summaries
            chunk_count = len(failure.chunks)
            if chunk_count > 0:
                context_summary.append(f"  + {chunk_count} conversation chunks with raw dialogue")

            failure_examples += f"""
Example {i}:
Question: {failure.question}
Expected Answer: {failure.correct_answer}
Model's Incorrect Answer: {failure.predicted_answer}
Why Incorrect: {failure.correctness_reasoning}
Context Available to Model:
{chr(10).join(context_summary)}
What Should Have Been Generated: {correct_answer}

---
"""

        prompt = f"""You are an expert at designing prompts for language models that need to work across diverse question types and topics in memory-based QA benchmarks.

CONTEXT:
I'm working on improving a benchmark prompt for the LongMemEval dataset. The current prompt is used to generate answers for questions across many different categories and topics. The category I'm focusing on is "{category}" but the prompt needs to work well for ALL categories in the benchmark.

CURRENT BENCHMARK PROMPT:
{original_prompt}

FAILURE ANALYSIS:
The current prompt is producing incorrect answers for questions in the "{category}" category. Here are the specific failure cases:

{failure_examples}

TASK:
Analyze these failure patterns and suggest improvements to the benchmark prompt. Your improvements should:

1. **Be general**: Work for the "{category}" category AND other categories in the benchmark
2. **Address root causes**: Fix the underlying issues causing these specific failures
3. **Maintain compatibility**: Don't break existing good performance on other question types
4. **Be specific**: Provide concrete guidance that helps the model generate more accurate answers

Focus on:
- What specific guidance is missing that would have prevented these errors?
- How can the prompt better handle the nuances of "{category}" questions?
- What instructions would help the model be more precise in its reasoning?

Please provide:
1. A brief analysis of the failure patterns you observe
2. Specific recommended changes to the prompt
3. The improved prompt with your changes highlighted

IMPROVED PROMPT:"""

        try:
            # Use retry function for prompt improvement generation
            response = await make_api_call_with_retry(
                client=self.client,
                model=self.llm_config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.2,
                seed=4242  # Same seed as used by LLMConfig
            )

            content = response.choices[0].message.content
            return content.strip() if content else "No improvements generated"
        except Exception as e:
            return f"Error generating prompt improvements: {str(e)}"

    async def test_prompt_performance(self, failures: List[FailureCase], prompt_template: str) -> float:
        """Test a prompt template against the failure cases and return success rate."""
        correct_count = 0
        total_count = len(failures)

        print(f"  Testing prompt performance on {total_count} failure cases...")

        for i, failure in enumerate(failures, 1):
            print(f"    Testing case {i}/{total_count}...", end="")

            try:
                # Recreate the exact same recall_result structure that the benchmark uses
                recall_result = {
                    "results": failure.retrieved_memories,
                    "chunks": failure.chunks,
                    "entities": {}
                }

                # Use the exact same context formatting as the benchmark (JSON format)
                context = json.dumps(recall_result)

                # Format the prompt exactly like the benchmark does
                prompt_content = prompt_template.format(
                    context_instructions="",  # Empty for default benchmark
                    question=failure.question,
                    formatted_question_date="Not specified",
                    context=context
                )

                # Generate answer using the test prompt with retry
                response = await make_api_call_with_retry(
                    client=self.client,
                    model=self.llm_config.model,
                    messages=[{"role": "user", "content": prompt_content}],
                    max_tokens=1000,
                    temperature=0.1,
                    seed=4242
                )

                candidate_answer = response.choices[0].message.content
                if not candidate_answer:
                    print(" SKIP (empty response)")
                    continue

                candidate_answer = candidate_answer.strip()

                # Validate with judge
                is_correct, judge_reasoning = await self.judge_answer(
                    failure.question,
                    failure.correct_answer,
                    candidate_answer,
                    failure.category
                )

                if is_correct:
                    correct_count += 1
                    print(" ✓")
                else:
                    print(" ✗")

            except Exception as e:
                print(f" ERROR: {str(e)}")
                continue

        success_rate = correct_count / total_count if total_count > 0 else 0.0
        print(f"  Prompt performance: {correct_count}/{total_count} = {success_rate:.2%}")
        return success_rate


async def main():
    """Main function to run the analysis."""
    parser = argparse.ArgumentParser(description="Analyze benchmark failures and suggest prompt improvements")
    parser.add_argument(
        "--category",
        type=str,
        required=True,
        help="Category to analyze (e.g., 'single-session-preference', 'multi-session')"
    )
    parser.add_argument(
        "--results-file",
        type=str,
        default="hindsight-dev/benchmarks/longmemeval/results/benchmark_results.json",
        help="Path to benchmark results JSON file"
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="Maximum number of failure examples to analyze"
    )
    parser.add_argument(
        "--optimize-prompt",
        action="store_true",
        help="Run iterative prompt optimization (25 rounds) to find best performing prompt"
    )

    args = parser.parse_args()

    # Convert to absolute path
    script_dir = Path(__file__).parent.parent
    results_path = script_dir / args.results_file

    if not results_path.exists():
        print(f"Error: Results file not found at {results_path}")
        return

    print(f"🔍 Analyzing failures for category: {args.category}")
    print(f"📄 Reading results from: {results_path}")

    analyzer = BenchmarkAnalyzer()

    # Load and analyze results
    results = analyzer.load_benchmark_results(results_path)
    failures = analyzer.extract_failures_by_category(results, args.category)

    if not failures:
        print(f"✅ No failures found for category '{args.category}'")
        return

    # Limit examples if requested (but not during optimization)
    total_failures = len(failures)
    if not args.optimize_prompt and len(failures) > args.max_examples:
        failures = failures[:args.max_examples]
        print(f"📊 Found {total_failures} failures (limited to {args.max_examples} for analysis)")
    else:
        print(f"📊 Found {len(failures)} failures")

    print("\n🤖 Generating judge-validated correct answers for failure cases...")
    correct_answers = []
    validation_stats = {"successful": 0, "failed": 0, "errors": 0}

    for i, failure in enumerate(failures, 1):
        print(f"  Processing example {i}/{len(failures)} (Question: {failure.question[:50]}...)")
        try:
            correct_answer = await analyzer.generate_correct_answer(failure)

            if correct_answer.startswith("Failed to generate"):
                print(f"    ❌ {correct_answer}")
                validation_stats["failed"] += 1
            else:
                print(f"    ✅ Judge-validated answer generated successfully")
                validation_stats["successful"] += 1

            correct_answers.append(correct_answer)
        except Exception as e:
            print(f"    💥 Error generating correct answer: {e}")
            correct_answers.append(f"Error: {str(e)}")
            validation_stats["errors"] += 1

    # Report validation statistics
    print(f"\n📈 Judge validation results:")
    print(f"  ✅ Successfully validated: {validation_stats['successful']}")
    print(f"  ❌ Failed to validate: {validation_stats['failed']}")
    print(f"  💥 Errors: {validation_stats['errors']}")

    print("\n💡 Generating prompt improvements...")
    try:
        improvements = await analyzer.suggest_prompt_improvements(failures, args.category, correct_answers)
        print(f"  Generated improvements: {len(improvements)} characters")
    except Exception as e:
        print(f"  Error generating improvements: {e}")
        improvements = f"Error generating improvements: {str(e)}"

    # Run iterative prompt optimization if requested
    best_prompt = None
    best_performance = 0.0
    optimization_history = []

    if args.optimize_prompt:
        print(f"\n🔄 Starting iterative prompt optimization (25 rounds)...")

        # Start with the original benchmark prompt
        current_prompt = analyzer.get_original_prompt_template()
        baseline_performance = await analyzer.test_prompt_performance(failures, current_prompt)

        print(f"\n📊 Baseline performance: {baseline_performance:.2%}")
        best_prompt = current_prompt
        best_performance = baseline_performance
        optimization_history.append({
            "round": 0,
            "performance": baseline_performance,
            "prompt": "Original benchmark prompt",
            "is_best": True
        })

        for round_num in range(1, 26):
            print(f"\n🔄 Round {round_num}/25: Analyzing current failures and generating improved prompt...")

            try:
                # Test current best prompt and collect new failures
                current_failures = []
                current_correct_answers = []

                print(f"  📊 Testing current prompt to identify remaining failures...")
                for i, failure in enumerate(failures, 1):
                    # Recreate the exact same recall_result structure
                    recall_result = {
                        "results": failure.retrieved_memories,
                        "chunks": failure.chunks,
                        "entities": {}
                    }
                    context = json.dumps(recall_result)

                    # Format the prompt exactly like the benchmark does
                    prompt_content = current_prompt.format(
                        context_instructions="",
                        question=failure.question,
                        formatted_question_date="Not specified",
                        context=context
                    )

                    # Generate answer using current prompt with retry
                    response = await make_api_call_with_retry(
                        client=analyzer.client,
                        model=analyzer.llm_config.model,
                        messages=[{"role": "user", "content": prompt_content}],
                        max_tokens=1000,
                        temperature=0.1,
                        seed=4242
                    )

                    candidate_answer = response.choices[0].message.content
                    if not candidate_answer:
                        # Still a failure
                        current_failures.append(failure)
                        current_correct_answers.append(failure.correct_answer)
                        continue

                    candidate_answer = candidate_answer.strip()

                    # Validate with judge
                    is_correct, judge_reasoning = await analyzer.judge_answer(
                        failure.question,
                        failure.correct_answer,
                        candidate_answer,
                        failure.category
                    )

                    if not is_correct:
                        # This is still a failure - add it to current failures for analysis
                        current_failures.append(failure)

                        # Generate what the correct answer should have been for this failure
                        correct_answer = await analyzer.generate_correct_answer(failure, max_attempts=3)
                        current_correct_answers.append(correct_answer)

                print(f"  🔍 Found {len(current_failures)} remaining failures to analyze")

                if len(current_failures) == 0:
                    print(f"  🎉 Perfect! No more failures - optimization complete!")
                    break

                # Generate a new improved prompt based on CURRENT failures
                improved_prompt = await analyzer.suggest_prompt_improvements(current_failures, args.category, current_correct_answers)

                # Extract the actual prompt from the improvements text
                if "IMPROVED PROMPT:" in improved_prompt:
                    prompt_start = improved_prompt.find("IMPROVED PROMPT:") + len("IMPROVED PROMPT:")
                    new_prompt = improved_prompt[prompt_start:].strip()
                elif "You are a helpful assistant" in improved_prompt:
                    prompt_start = improved_prompt.find("You are a helpful assistant")
                    new_prompt = improved_prompt[prompt_start:].strip()
                else:
                    print(f"  ❌ Could not extract prompt from improvements, using current prompt")
                    new_prompt = current_prompt

                # Test the new prompt on ALL original failures
                performance = await analyzer.test_prompt_performance(failures, new_prompt)

                is_better = performance > best_performance
                optimization_history.append({
                    "round": round_num,
                    "performance": performance,
                    "prompt": "Generated improved prompt",
                    "is_best": is_better,
                    "failures_analyzed": len(current_failures)
                })

                if is_better:
                    print(f"  🎉 New best performance: {performance:.2%} (improved by {(performance - best_performance):.1%})")
                    best_prompt = new_prompt
                    best_performance = performance
                    current_prompt = new_prompt
                else:
                    print(f"  📉 Performance: {performance:.2%} (no improvement)")
                    # Don't update current_prompt - keep using the best one

            except Exception as e:
                print(f"  💥 Error in round {round_num}: {str(e)}")
                optimization_history.append({
                    "round": round_num,
                    "performance": 0.0,
                    "prompt": f"Error: {str(e)}",
                    "is_best": False,
                    "failures_analyzed": 0
                })

        print(f"\n🏆 Optimization complete!")
        print(f"  📈 Best performance achieved: {best_performance:.2%}")
        print(f"  📊 Improvement over baseline: {(best_performance - baseline_performance):.1%}")

    # Save results
    output_dir = script_dir / "results" / "prompt_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{args.category}_analysis.md"

    # Create detailed report
    report = f"""# Benchmark Failure Analysis: {args.category}

## Summary
- **Category**: {args.category}
- **Total Failures Analyzed**: {len(failures)}
- **Judge-Validated Answers Generated**: {validation_stats['successful']}/{len(failures)}
- **Results File**: {results_path}

## Judge Validation Process
This analysis uses a new approach where generated "correct" answers are validated using the exact same judge logic as the benchmark. We attempt up to 10 times to generate an answer that the judge accepts as correct, ensuring that our prompt improvements are based on truly correct examples.

- ✅ **Successfully validated**: {validation_stats['successful']} answers
- ❌ **Failed to validate**: {validation_stats['failed']} answers
- 💥 **Errors**: {validation_stats['errors']} answers

## Failure Cases

"""

    for i, (failure, correct_answer) in enumerate(zip(failures, correct_answers), 1):
        report += f"""### Example {i}

**Question**: {failure.question}

**Expected Answer**: {failure.correct_answer}

**Model's Answer**: {failure.predicted_answer}

**Why Incorrect**: {failure.correctness_reasoning}

**Generated Correct Answer**: {correct_answer}

**Retrieved Memories**:
"""
        for j, memory in enumerate(failure.retrieved_memories, 1):
            memory_text = memory.get('text', '')
            # Truncate memory text for markdown output only
            truncated_text = memory_text[:200] + "..." if len(memory_text) > 200 else memory_text
            report += f"- **Memory {j}**: {truncated_text}\n"

        # Add chunks information
        report += f"\n**Conversation Chunks**: {len(failure.chunks)} chunks containing raw dialogue\n"
        if failure.chunks:
            report += "- Chunk IDs: " + ", ".join(list(failure.chunks.keys())[:5])  # Show first 5 chunk IDs
            if len(failure.chunks) > 5:
                report += f" ... and {len(failure.chunks) - 5} more"
            report += "\n"

        report += "\n---\n\n"

    report += f"""## Prompt Improvement Analysis

{improvements}
"""

    # Add optimization results if optimization was run
    if args.optimize_prompt and optimization_history:
        report += f"""
## Iterative Prompt Optimization Results

### Performance Summary
- **Baseline Performance**: {optimization_history[0]['performance']:.2%}
- **Best Performance Achieved**: {best_performance:.2%}
- **Improvement**: {(best_performance - optimization_history[0]['performance']):.1%}
- **Total Optimization Rounds**: 25

### Optimization History
| Round | Performance | Improvement | Failures Analyzed | Best So Far |
|-------|-------------|-------------|-------------------|-------------|
"""
        for entry in optimization_history:
            is_best_marker = "🏆" if entry['is_best'] else ""
            improvement = f"+{(entry['performance'] - optimization_history[0]['performance']):.1%}" if entry['performance'] > optimization_history[0]['performance'] else f"{(entry['performance'] - optimization_history[0]['performance']):.1%}"
            failures_count = entry.get('failures_analyzed', 'N/A')
            report += f"| {entry['round']} | {entry['performance']:.2%} | {improvement} | {failures_count} | {is_best_marker} |\n"

        report += f"""
### Best Performing Prompt
```
{best_prompt}
```
"""

    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\n✅ Analysis complete!")
    print(f"📄 Report saved to: {output_file}")
    print(f"\n🔍 Key findings:")
    print(f"  - {len(failures)} failure cases analyzed")
    print(f"  - {validation_stats['successful']}/{len(failures)} judge-validated correct answers generated")
    print(f"  - Prompt improvements generated using validated answers")
    if args.optimize_prompt and optimization_history:
        print(f"  - Iterative optimization completed: {best_performance:.2%} best performance")
        improvement_pct = (best_performance - optimization_history[0]['performance']) * 100
        print(f"  - Performance improvement: {improvement_pct:+.1f} percentage points")
    print(f"  - Detailed report available at {output_file}")


if __name__ == "__main__":
    asyncio.run(main())