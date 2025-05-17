from anthropic import Anthropic
from dotenv import load_dotenv
import sqlite3
from sample_code import execute_sql_query
import math

load_dotenv()

client = Anthropic()

# Helper function to get the database schema so that we can pass it to Claude
def get_database_schema(db_path):
    """One-liner to get table and column names"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [table[0] for table in cursor.fetchall()]
    
    result = {}
    for table in tables:
        cursor.execute(f"SELECT name FROM PRAGMA_TABLE_INFO('{table}')")
        result[table] = [column[0] for column in cursor.fetchall()]
    
    conn.close()

    return result

# Function with improved prompting to improve Claude's accuracy in returning SQL queries
def get_query(question):

    # First, get the schema for the database we want to query
    schema = get_database_schema("nba.sqlite")
    
    # Second, define examples for few-shot prompting
    aggregation_query_example = {
        "natural_language": "What's the average points per game?",
        "sql": "SELECT ROUND(AVG(pts_home + pts_away) / 2, 2) as avg_points FROM game LIMIT 1",
        "type": "aggregation"
    }

    count_query_example = {
        "natural_language": "How many games went to overtime?",
        "sql": "SELECT COUNT(*) as ot_games FROM line_score WHERE pts_ot1_home IS NOT NULL LIMIT 1",
        "type": "counting"
    }

    ranking_query_example = {
        "natural_language": "Which team has the most home games?",
        "sql": "SELECT t.full_name FROM game g JOIN team t ON g.team_id_home = t.id GROUP BY t.id, t.full_name ORDER BY COUNT(*) DESC LIMIT 1",
        "type": "ranking"
    }

    filtering_query_example = {
        "natural_language": "List all players from Spain",
        "sql": "SELECT first_name, last_name FROM common_player_info WHERE country = 'Spain'",
        "type": "filtering"
    }

    # Third, provide full context to the model.
    sql_query = client.messages.create(
        model = "claude-3-7-sonnet-20250219",
        max_tokens = 1000,
        system = f"You're an experienced database analyst. Your job is to convert user questions to SQL query. Here's the database schema that you should reference: {schema}",
        messages = [
            {
                "role":"user", "content": [
                    {"type":"text", "text":f"Convert this question to SQL: {question}. Provide just SQL statement text in one line, and nothing else. Don't forget to end queries with ;"},
                    {"type":"text", "text":f"Count query example: {count_query_example}"},
                    {"type":"text", "text":f"Aggregation query example: {aggregation_query_example}"},
                    {"type":"text", "text":f"Ranking query example: {ranking_query_example}"},
                    {"type":"text", "text":f"Filtering query example: {filtering_query_example}"},
                ]
            }
        ]
    )

    return sql_query.content[0].text

# Helper to run the real and the generated queries and obtain results
def run_query(db_path, true_query, claude_query):

    result_true = execute_sql_query(db_path, true_query)
    result_generated = execute_sql_query(db_path, claude_query)

    return result_true, result_generated

# Obtain all results for both real and generated queries, returns an object with results to be analyzed
def run_all_queries(db_path="nba.sqlite", ground_truth=None):

    results = []

    db_path = db_path
    
    for nl_query in ground_truth:

        true_query = nl_query['sql']
        claude_query = get_query(nl_query["natural_language"])

        print(f"evaluating {nl_query['natural_language']}")

        true_query_result, gen_query_result = run_query(db_path, true_query, claude_query)

        results.append(
            {
                "text":nl_query["natural_language"], 
                "true_query":true_query, 
                "true_query_result":true_query_result,
                "claude_query":claude_query,
                "claude_query_result":gen_query_result
            }
        )

    return results

# Helper to quickly evalute the number of correct, incorrect, and errored queries. This does not take into account correct results that are formatted differently.
def quick_evaluate_performance(results, ground_truth):

    correct = 0
    error = 0
    incorrect = 0
    incorrect_idx = []

    i = 0

    for result in results:
        
        true_result = result['true_query_result']
        claude_result = result['claude_query_result']

        # The calculation for some correct queries is pretty straight forward. If the outputs match, then it's certainly correct
        if true_result == claude_result:
            correct += 1

        # Now let's calculate the amount of errored queries due to syntax/incorrect column/table names. They return None in that case
        elif claude_result == None:
            error += 1

        # The third scenario is the hardest to analyze. Several queries returned incorrect values. However, plenty also returned correct values in different formats OR with differences in rounding.
        else:
            incorrect += 1
            incorrect_idx.append(i)
        
        i += 1

    print(f"Total questions: {len(ground_truth)}")
    print(f"Correct: {correct}")
    print(f"Errors: {error}")
    print(f"Incorrect: {incorrect}")
    print(f"Accuracy: {(correct / (len(ground_truth)) * 100)}")

    return correct, error, incorrect, incorrect_idx

# Uses Claude to evaluate if two queries are equivalent, even if they differ in formatting.
def are_results_equivalent(result):

    if len(result['claude_query_result']) > 1000 or len(result['true_query_result']) > 1000:
        return "Incorrect"

    output = client.messages.create(
        model = "claude-3-7-sonnet-20250219",
        max_tokens = 50,
        messages = [
            {
                "role":"user", "content": [
                    {"type":"text", "text":"Analyze whether the two answers to the question are equivalent. When analyzing the 'claude_query_result' vs 'true_query_result' fields, consider them equivalent if the claude_query_result contains all the essential entities from true_query_result, even if presented with additional information or in a different structure.. If two numerical results are within 1.0 of each other, consider that correct. Reply only with Correct or Incorrect"},
                    {"type":"text", "text":f"Question: {result['text']}"},
                    {"type":"text", "text":f"true_query_result: {result['true_query_result']}"},
                    {"type":"text", "text":f"claude_query_result: {result['claude_query_result']}"}
                ]
            }
        ]
    )

    return output.content[0].text

# Evaluates all queries and return total performance of the prompting when compared to ground truth
def claude_evaluate_performance(results, ground_truth):
    
    correct, error, incorrect, incorrect_idx = quick_evaluate_performance(results, ground_truth)

    pseudo_correct = 0

    for idx in incorrect_idx:
        if are_results_equivalent(results[idx]) == "Correct":
            pseudo_correct += 1
    
    print(f"Total questions: {len(ground_truth)}")
    print(f"Correct: {correct}")
    print(f"Pseudo-correct: {pseudo_correct}")
    print(f"Errors: {error}")
    print(f"Incorrect: {incorrect}")
    print(f"Accuracy: {(correct + pseudo_correct / (len(ground_truth)) * 100)}")

    return correct, error, incorrect, pseudo_correct