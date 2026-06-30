import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "agent"))

from search import build_search_queries, execute_searches

customer = {
    "name": "Elodie Torre",
    "company": "Elodie Torre Photographe",
    "email": "",
    "phone": "",
    "address": "France"
}

queries = build_search_queries(customer)

print("生成搜索词:")
for q in queries:
    print(f"[{q['channel']}] ({q['priority']}) -> {q['query']}")

print("\n开始搜索...")

results = execute_searches(
    queries[:3],
    max_results_per_query=3
)

print("\n结果数量:", len(results))

for r in results:
    print("----------------")
    print(r["url"])
    print(r["title"])
