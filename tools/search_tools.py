import arxiv
from google.genai import types
from tools.client import get_client, retry_call

FLASH_MODEL = "gemini-2.5-flash"


def search_arxiv(query: str, max_results: int = 3) -> str:
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results)
    results = []
    for paper in client.results(search):
        year = paper.published.year if paper.published else "연도 미상"
        results.append(
            f"제목: {paper.title}\n"
            f"연도: {year}\n"
            f"요약: {paper.summary[:300]}..."
        )
    if not results:
        return "검색 결과 없음"
    return "\n\n".join(results)


def search_with_google(query: str) -> str:
    client = get_client()
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    response = retry_call(lambda: client.models.generate_content(
        model=FLASH_MODEL,
        contents=query,
        config=types.GenerateContentConfig(tools=[google_search_tool]),
    ))
    return response.text
